import torch
import argparse
import yaml
import math, random
from torch import Tensor
from torch.nn import functional as F
from pathlib import Path
from torchvision import io
from semseg.utils.utils import timer
from semseg.utils.visualize import draw_text
import torch.utils.data as data
from torchvision import transforms
from rich.console import Console
import numpy as np
from matplotlib import pyplot as plt
import cv2
from collections import OrderedDict
import copy
from torch.utils.data import DataLoader
from torchvision.utils import make_grid
from tools.val import Pgd_Attack, clean_accuracy
from PIL import Image, ImageDraw, ImageFont
import gc
from autoattack.other_utils import check_imgs
import torch.nn as nn
from functools import partial
from semseg.utils.visualize import generate_palette
from semseg.models import *
from semseg.datasets import * 
from semseg.augmentations import get_train_augmentation, get_val_augmentation
from semseg.losses import get_loss
from semseg.schedulers import get_scheduler
from semseg.optimizers import get_optimizer, create_optimizers, adjust_learning_rate
from semseg.utils.utils import fix_seeds, setup_cudnn, cleanup_ddp, setup_ddp, Logger, makedir, normalize_model
from val import evaluate, Pgd_Attack
import semseg.utils.attacker as attacker
import semseg.datasets.transform_util as transform
from semseg.metrics import Metrics
import torchvision
from fvcore.nn import FlopCountAnalysis, flop_count_table, flop_count_str
# from mmcv.utils import Config
# from mmcv.runner import get_dist_info
from semseg.datasets.dataset_wrappers import *
console = Console()
SEED = 225
random.seed(SEED)
np.random.seed(SEED)

g = torch.Generator()
g.manual_seed(SEED)

def seed_worker(worker_id):
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)


def sizeof_fmt(num, suffix="Flops"):
    for unit in ["", "Ki", "Mi", "G", "T"]:
        if abs(num) < 1000.0:
            return f"{num:3.3f}{unit}{suffix}"
        num /= 1000.0
    return f"{num:.1f}Yi{suffix}"

IN_MEAN = [0.485, 0.456, 0.406]
IN_STD = [0.229, 0.224, 0.225]

def clean_accuracy(
    model, data_loder, n_batches=-1, n_cls=21, return_output=False, ignore_index=-1, return_preds=False):
    """Evaluate accuracy."""

    model.eval()
    acc = 0
    acc_cls = torch.zeros(n_cls)
    n_ex = 0
    n_pxl_cls = torch.zeros(n_cls)
    int_cls = torch.zeros(n_cls)
    union_cls = torch.zeros(n_cls)
    # if logger is None:
    #     logger = Logger(None)
    l_output = []
    #print('Using {n_cls} classes and ignore')

    metrics = Metrics(n_cls, -1, 'cpu')

    for i, vals in enumerate(data_loder):
        if False:
            print(i)
        else:
            input, target = vals[0], vals[1]
            #print(input[0, 0, 0, :10])
            print(input[0, 0, 0, :10], input.min(), input.max(),
                target.min(), target.max())
            input = input.cuda()

            with torch.no_grad():
                output = model(input)
            # l_output.append(output.cpu())
            #print('fp done')
            #metrics.update(output.cpu(), target)

            pred = output.max(1)[1].cpu()
            l_output.append(pred.cpu())
            pred[target == ignore_index] = ignore_index
            acc_curr = pred == target
            #print('step 1 done')

            # Compute correctly classified pixels for each class.
            for cl in range(n_cls):
                ind = target == cl
                acc_cls[cl] += acc_curr[ind].float().sum()
                n_pxl_cls[cl] += ind.float().sum()
            #print(acc_cls, n_pxl_cls)
            ind = n_pxl_cls > 0
            m_acc = (acc_cls[ind] / n_pxl_cls[ind]).mean()

            # Compute overall correctly classified pixels.
            #acc_curr = acc_curr.float().view(input.shape[0], -1).mean(-1)
            #acc += acc_curr.sum()
            a_acc = acc_cls.sum() / n_pxl_cls.sum()
            n_ex += input.shape[0]
            #print('step 2 done')

            # Compute intersection and union.
            intersection_all = pred == target
            #pred[target == 0] = 0
            for cl in range(n_cls):
                ind = target == cl
                int_cls[cl] += intersection_all[ind].float().sum()
                union_cls[cl] += (ind.float().sum() + (pred == cl).float().sum()
                                  - intersection_all[ind].float().sum())
            ind = union_cls > 0
            #ind[0] = False
            m_iou = (int_cls[ind] / union_cls[ind]).mean()

            print(
                f'batch={i} running mAcc={m_acc:.2%} running aAcc={a_acc.mean():.2%}',
                f' running mIoU={m_iou:.2%}')

        #print(metrics.compute_iou()[1], metrics.compute_pixel_acc()[1])

        if i + 1 == n_batches:
            print('enough batches seen')
            break

    # logger.log(f'mAcc={m_acc:.2%} aAcc={a_acc:.2%} mIoU={m_iou:.2%} ({n_ex} images)')
    #print(acc_cls / n_pxl_cls)
    #print(acc_cls.sum() / n_pxl_cls.sum())
    l_output = torch.cat(l_output)
    stats = {
        'mAcc': m_acc.item(),
        'aAcc': a_acc.item(),
        'mIoU': m_iou.item()}

    return stats, l_output



def evaluate(val_loader, model, attack_fn, n_batches=-1, args=None):
    """Run attack on points."""

    model.eval()
    adv_loader = []

    for i, (input, target) in enumerate(val_loader):
        print(input[0, 0, 0, :10])
        input = input.cuda()
        target = target.cuda()

        x_adv, _, acc = attack_fn(model, input.clone(), target)
        check_imgs(input, x_adv, norm=args.norm)
        if False:
            print(f'batch={i} avg. pixel acc={acc.mean():.2%}')

        adv_loader.append((x_adv.cpu(), target.cpu().clone()))
        if i + 1 == n_batches:
            break

    return adv_loader



def get_data(dataset_cfg, test_cfg):

    if str(test_cfg['NAME']) == 'pascalvoc':
        data_dir = '../VOCdevkit/'
        val_data = get_segmentation_dataset(test_cfg['NAME'],
            root=dataset_cfg['ROOT'],
            split='val',
            transform=torchvision.transforms.ToTensor(),
            base_size=512,
            crop_size=(473, 473))

    elif str(test_cfg['NAME']) == 'pascalaug':
        val_data = get_segmentation_dataset(test_cfg['NAME'],
            root=dataset_cfg['ROOT'],
            split='val',
            transform=torchvision.transforms.ToTensor(),
            base_size=512,
            crop_size=(473, 473))

    elif str(test_cfg['NAME']).lower() == 'ade20k':
        val_data = get_segmentation_dataset(test_cfg['NAME'],
            root=dataset_cfg['ROOT'],
            split='val',
            transform=torchvision.transforms.ToTensor(),
            base_size=520,
            crop_size=(512, 512))
    else:
        raise ValueError(f'Unknown dataset.')

    val_loader = torch.utils.data.DataLoader(
        val_data, batch_size=test_cfg['BATCH_SIZE'], shuffle=False,
        num_workers=2, pin_memory=True, sampler=None, worker_init_fn =seed_worker, generator=g)

    return val_loader



# alpha, num_iters
attack_setting = {'pgd': (0.01, 40), 'segpgd': (0.01, 40),
                    'cospgd': (0.15, 40),
                    'maskpgd': (0.15, 40)}



class MaskClass(nn.Module):

    def __init__(self, ignore_index: int) -> None:
        super().__init__()
        self.ignore_index = ignore_index

    def forward(self, input: Tensor) -> Tensor:
        if self.ignore_index == 0:
            return input[:, 1:]
        else:
            return torch.cat(
                (input[:, :self.ignore_index],
                 input[:, self.ignore_index + 1:]), dim=1)


def mask_logits(model: nn.Module, ignore_index: int) -> nn.Module:
    # TODO: adapt for list of indices.
    layers = OrderedDict([
        ('model', model),
        ('mask', MaskClass(ignore_index))
    ])
    return nn.Sequential(layers)

los_pairs = [['mask-ce-avg'], ['segpgd-loss'], ['js-avg'], ['mask-norm-corrlog-avg']]

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cfg', type=str, default='configs/ade20k_cnvxt_cvst.yaml')
    parser.add_argument('--eps', type=float, default=1.)
    parser.add_argument('--store-data', action='store_true', help='PGD data?', default=False)
    parser.add_argument('--n_iter', type=int, default=100)
    parser.add_argument('--adversarial', action='store_true', help='adversarial eval?', default=True)
    parser.add_argument('--attack', type=str, default='segpgd-loss', help='pgd, cospgd-loss, ce-avg or mask-ce-avg, segpgd-loss, mask-norm-corrlog-avg, js-avg?')
    parser.add_argument('--attack_type', type=str, default='apgd-larg-eps', help='apgd or apgd-larg-eps?')
    parser.add_argument('--pair', type=int, default=0, help='0, 1 or 2')

    args = parser.parse_args()

    with open(args.cfg) as f:
        cfg = yaml.load(f, Loader=yaml.SafeLoader)

    dataset_cfg, model_cfg, test_cfg = cfg['DATASET'], cfg['MODEL'], cfg['EVAL']

    model = eval(model_cfg['NAME'])(test_cfg['BACKBONE'], test_cfg['N_CLS'],None)
    # model = eval(model_cfg['NAME'])

    ckpt = torch.load(test_cfg['MODEL_PATH'], map_location='cpu')
    # print(ckpt.keys())
    # exit()
    for k in ['image_encoder.neck.0.weight', 'image_encoder.neck.1.weight', 'image_encoder.neck.1.bias', 'image_encoder.neck.2.weight', 'image_encoder.neck.3.weight', 'image_encoder.neck.3.bias']:
        ckpt.pop(k, None)
    ckpt1 = copy.deepcopy(ckpt)
    # print(ckpt1.keys())
    for k in ckpt.keys():
        if 'decode_head' in k:
            ckpt1.pop(k, None)
        elif 'auxiliary_head' in k:
            ckpt1.pop(k, None)
    # print(ckpt1.keys())
    # exit()
    torch.save(ckpt1, '/data/naman_deep_singh/model_zoo/convnext_S_backbone_Uper.pt')
    exit()



    model.load_state_dict(torch.load(test_cfg['MODEL_PATH'], map_location='cpu'))
    # checkpoint = torch.load(test_cfg['MODEL_PATH'],  map_location='cpu')
    # model.load_state_dict(checkpoint['state_dict'], strict=False)
    model_norm = False
    if model_norm:
        print('Add normalization layer.')   
        model = normalize_model(model, IN_MEAN, IN_STD)
    # model = mask_logits(model, 0)
    # model.eval()
    # inpp = torch.rand(1, 3, 512, 512)
    # flops = FlopCountAnalysis(model, inpp)
    # val = flops.total()
    # print(val)
    # print(sizeof_fmt(int(val)))
    # print(flop_count_table(flops, max_depth=2))
    # print(flops.by_operator())
    # PSPNet_DDCAT(layers=50, classes=21, zoom_factor=8, pretrained=False)

    model = model.to('cuda')

    val_data_loader = get_data(dataset_cfg, test_cfg)

    # clean_accuracy(model, dataloader)
    # exit()
    console.print(f"Model > [yellow1]{cfg['MODEL']['NAME']} {test_cfg['BACKBONE']}[/yellow1]")
    console.print(f"Dataset > [yellow1]{test_cfg['NAME']}[/yellow1]")

    save_dir = Path(cfg['SAVE_DIR']) / 'test_results'
    save_dir.mkdir(exist_ok=True)

    preds = []
    lblss = []

    # clean_stats, _ = clean_accuracy(model, val_data_loader, n_batches=-1, n_cls=test_cfg['N_CLS'], ignore_index=-1)
    # print(clean_stats)
    # exit()
    # if '5iter' in test_cfg['MODEL_PATH']:
    #     fold = '5iter_ade'
    #     if 'clean_init_5iter' in test_cfg['MODEL_PATH']:
    #         appen = 'clean_5iter_ADE'
    #     else:
    #         appen = '5iter_ADE'
    # elif '2_iter' in test_cfg['MODEL_PATH']: 
    #     fold = '2iter_ade'
    #     appen = '2iter_ADE'
        
    # elif 'ConvNeXt-S_CVST_ROB' in test_cfg['MODEL_PATH']:
    #     fold = 'S_model'
    #     appen = 'S_ADE'
    # elif 'ddcat_pspnet50' in test_cfg['MODEL_PATH']:
    #     fold = '2iter_rob_model'
    #     appen = 'DDCAT'
    # else:
    #     fold = 'clean_model_out'
    #     print(test_cfg['MODEL_PATH'])
    #     if '5iter_300ep' in test_cfg['MODEL_PATH']:
    #         appen = 'c_init_5iter_300'
    #     elif '5iter_100' in test_cfg['MODEL_PATH']:
    #         appen = 'c_init_5iter_100'
    #     elif '5iter_50' in test_cfg['MODEL_PATH']:
    #         appen = 'c_init_5iter_50'
    #     elif '2iter_50ep' in test_cfg['MODEL_PATH']:
    #         appen = 'c_init_2iter_50'
    #     else:
    #         appen = 'c_init_2iter_200'
    fold = '5iter_ade'
    appen = 'SEGMENTER'
    # print(appen)
    # exit()
    for ite, ls in enumerate(los_pairs[args.pair]):
        # args.eps = ls #'segpgd-loss' 
        args.attack = ls
        if args.adversarial:
            strr = f"adversarial_{test_cfg['NAME']}_{args.attack_type}_{fold}_SD_{SEED}"
        else:
            strr = f"clean_{test_cfg['NAME']}"
        # args.eps = ls
        if args.adversarial:
            n_batches = -1
            # norm = 'Linf'
            args.norm = 'Linf'

            if args.norm == 'Linf' and args.eps >= 1.:
                args.eps /= 255.

            attack_pgd = Pgd_Attack(epsilon=args.eps, alpha=1e-2, num_iter=100, los=args.attack) if args.attack_type == 'pgd' else None
            if args.attack_type == 'apgd':
                attack_fn = partial(
                    attacker.apgd_restarts,
                    norm=args.norm,
                    eps=args.eps,
                    n_iter=args.n_iter,
                    n_restarts=1,
                    use_rs=True,
                    loss=args.attack if args.attack else 'ce-avg',
                    verbose=True,
                    track_loss='norm-corrlog-avg' if args.attack == 'mask-norm-corrlog-avg' else 'ce-avg',    
                    log_path=None,
                    early_stop=True
                    )
            else:
                args.n_iter = 300
                attack_fn =  partial(
                    attacker.apgd_largereps,
                    norm=args.norm,
                    eps=args.eps,
                    n_iter=args.n_iter,
                    n_restarts=1, #args.n_restarts,
                    use_rs=True,
                    loss=args.attack if args.attack else 'ce-avg',
                    verbose=True,
                    track_loss='norm-corrlog-avg' if args.attack == 'mask-norm-corrlog-avg' else 'ce-avg',
                    log_path=None,
                    early_stop=True)
            adv_loader = evaluate(val_data_loader, model, attack_fn, n_batches, args)

        if args.adversarial:
            adv_stats, l_outs = clean_accuracy(model, adv_loader, -1, n_cls=dataset_cfg['N_CLS'], ignore_index=-1)
            torch.save(l_outs, cfg['SAVE_DIR'] + f"/test_results/output_logits_new/{fold}/preds/" + f"{args.attack_type}_{args.attack}_{appen}_mod_rob_mod_{args.eps:.4f}_n_it_{args.n_iter}_{test_cfg['NAME']}_{test_cfg['BACKBONE']}_SD_{SEED}_MAX.pt")
            adv = torch.cat([x for x, y in adv_loader], dim=0).cpu()
            data_dict = {'adv': adv}
            print(data_dict['adv'].shape)
            # torch.save(data_dict, cfg['SAVE_DIR'] + f"/test_results/output_logits_new/{fold}/images/" + f"{args.attack_type}_{args.attack}_{appen}_mod_rob_mod_{args.eps:.4f}_n_it_{args.n_iter}_{test_cfg['NAME']}_{test_cfg['BACKBONE']}_SD_{SEED}.pt")

        with open(cfg['SAVE_DIR'] + f"/test_results/output_logits_new/{fold}/logs/"+ f"{args.attack_type}_{args.attack}_{appen}_mod_rob_mod_{args.eps:.4f}_n_it_{args.n_iter}_{test_cfg['NAME']}_{test_cfg['BACKBONE']}_SD_{SEED}.txt", 'a+') as f:
            if ite == 0:
                f.write(f"{cfg['MODEL']['NAME']} - {test_cfg['BACKBONE']}\n")
                f.write(f"Clean results: {clean_stats}\n")
                f.write(f"{str(test_cfg['MODEL_PATH'])}\n")
            if args.adversarial:
                f.write(f"----- Linf radius: {args.eps:.4f} ------")
                f.write(f"Attack: {args.attack_type} {args.attack} \t \t Iterations: {args.n_iter} \t alpha: 0.01 \n")   
                f.write(f"Adversarial results: {adv_stats}\n") 
                # f.write(f"Adversarial mIoU: {adv_miou:.2%} \t mAcc: {adv_macc:.2%}\t aAcc: {adv_aacc:.2%}\n")
            f.write("\n")
        console.rule(f"[cyan]Segmentation results are saved in {cfg['SAVE_DIR']}" + f"/test_results/output_logits_new/{fold}/preds/" + f"{args.attack_type}_{args.attack}_{appen}_mod_rob_mod_{args.eps:.4f}_n_it_{args.n_iter}_{test_cfg['NAME']}_{test_cfg['BACKBONE']}_SD_{SEED}")