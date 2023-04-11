#!/bin/bash

export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
# /scratch/nsingh/At_ImageNet/effnet_b4_100_epochs_not_orig.yaml
# rn50_configs/rn50_16_epochs.yaml
# chkpt = '/mnt/SHARED/nsingh/ImageNet_Arch/model_2022-10-11 17:43:32_effnet_b4_iso_0_not_orig_1_clean/weights_45.pt'
# #--config-file $1 \
sleep 2s

# conda activate ffcv

python3 ./tools/train.py --cfg ./configs/ade20k_cvst_vena.yaml --world_size 8