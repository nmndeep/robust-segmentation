import math
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
import torch
from palettable.tableau import GreenOrange_12, TableauMedium_10, Tableau_20, ColorBlind_10 
from palettable.cartocolors.qualitative import Bold_8, Prism_10, Vivid_10, Safe_10
from palettable.colorbrewer.qualitative import Accent_8 
from palettable.cartocolors.sequential import DarkMint_4, Magenta_4, TealGrn_4, PurpOr_4
plt.rcParams["font.family"] = "Times New Roman"

new_colors = np.vstack((ColorBlind_10.mpl_colors, Bold_8.mpl_colors))
my_cmap = ListedColormap(new_colors, name='BoldBlind')
my_cmap2 = ListedColormap(Tableau_20.mpl_colors)
sequent = np.vstack((TealGrn_4.mpl_colors, Magenta_4.mpl_colors, DarkMint_4.mpl_colors, PurpOr_4.mpl_colors))
my_cmap3 = ListedColormap(Prism_10.mpl_colors)
my_cmap4 = ListedColormap(sequent)
# mcmap = my_cmap1 +  my_cmap2
# sns.set_style("darkgrid")
sns.set_style("whitegrid", {"grid.color": ".8", "grid.linestyle": "--"})
sns.despine(left=True)
# from tueplots import bundles
plt.rcParams.update({'text.usetex': False,
 'font.serif': ['Times New Roman'],
 'mathtext.fontset': 'stix',
 'mathtext.rm': 'Times New Roman',
 'mathtext.it': 'Times New Roman:italic',
 'mathtext.bf': 'Times New Roman:bold',
 'font.family': 'serif'})

## some plotting stas helper functions
def round_near_five(x, base=5):
    return base * round(x/base)

models = ["pgd_5step", "apgd_5step"] #, "vit_s_cvst_25ep_final3", "vit_s_cvst_25ep_convstem_high_lr"] #, "conviso_cvblk_300AT", "conviso_300AT"] #, "base_cvblk"] #, "tb10_model4", "tb10_model5", "model1"]
# l2s = [model0, model3, model5, model6, model7, model8]
train_stats = []
for m in models:
    print(m)
    with open(f"/Users/nmndeep/Documents/logs_semseg/{m}_log.txt", 'r') as fp:
        # lines to read
        # if "300" in m:
        line_numbers = np.arange(0,50,1)
        # else:
        #     line_numbers = np.arange(0,49,2)
        cnvnxt = []
        for i, line in enumerate(fp):
            # read line 4 and 7
            print(line)
            if i in line_numbers:
                i_0 = (line.index("Loss"))
                i_1 = (line.index("Cost"))
                cnvnxt.append(float(line[i_0+6:i_1-6]))
        train_stats.append(cnvnxt)
print(train_stats)
aa_lo_eps = [92.9, 73.8, 68.0, 64.7, 63.1, 62.4, 62.2]
aa_hi_eps = [92.9, 43.4, 28.5, 20.2, 17.2, 15.9, 15.6]
mi_lo_eps = [75.9, 39.2, 33.1, 30.1, 29.2, 28.8, 28.2]
mi_hi_eps = [75.9, 13.3, 7.3, 5.1, 4.3, 3.9, 3.6]
# train_stats = [t1_rob, t1_clean]
fig = plt.figure(figsize=(14,8))
# plt.title("Training curves")
# xx1 = [1]
# xx = ["Rand-init", "1k-init", "3-Aug", "RandAug+CM+MU+LS", "CvBlk", "Long-Train", "Base"]
# xx1 = (list(np.arange(1,51,1)))
xx1 = [0, 10, 25, 50, 100, 150, 200]
# plt.plot(xx1[4:], train_stats[0][4:], linewidth=1.5, color = my_cmap2(12), label=models[0])
# plt.plot(xx1[4:], train_stats[1][4:], linewidth=1.5, color = my_cmap2(0), label=models[1])
plt.plot(xx1, aa_lo_eps, linewidth=2.5, color = my_cmap4(11), marker='o', label="Attack radius, $\ell_\infty$=8/255")
plt.plot(xx1, aa_hi_eps, linewidth=2.5, color = my_cmap(14), marker='o', label="Attack radius, $\ell_\infty$=12/255")
plt.plot(xx1, mi_lo_eps, linewidth=2.5, color = my_cmap4(11),  linestyle= '--', marker='o')
plt.plot(xx1, mi_hi_eps, linewidth=2.5, color = my_cmap(14), linestyle= '--', marker='o')
# plt.plot(xx1, train_stats[1], linewidth=1.5, color = my_cmap2(0), label="Clean")

# plt.annotate('lr-peak', xy=(xx2[65], train_stats[0][65]+.1))
# plt.title("Mask-Margin-APGD Acc and mIoU at different perturbation radii v.s the number of iterations")
# # plt.plot(xx1[10:49], cnvnxte4[10:], linewidth=1.5, color = my_cmap(11), linestyle ="--", label="convnext-b-1e-3_epoch10onwards")
# # plt.plot(xx1[10:46], cnvnxtcvb4[10:], linewidth=1.5, color = my_cmap(0), linestyle ="--",  label="convnext-b-cvblk1e-3_epoch10onwards")
plt.xlabel("Number of iterations", fontsize=23)
plt.xticks(xx1, fontsize=22)
plt.yticks(fontsize=22)
plot_lines = [Line2D([0], [0], color=my_cmap4(11), linewidth=3), Line2D([0], [0], color=my_cmap(14), linewidth=3, linestyle ='--')]
labels = ['Acc.', 'mIoU']
plt.ylabel("Metric (%)", fontsize=23)
legend1 = plt.legend(plot_lines, labels, loc=9, fontsize=22, bbox_to_anchor=(.5,1.0),
          fancybox=False)
plt.gca().add_artist(legend1)
plt.legend(fontsize=22, bbox_to_anchor=(1.01,1.0),
          fancybox=False, shadow=False)
# plt.show()
plt.savefig("/Users/nmndeep/Documents/logs_semseg/iterations_over_attack.pdf", dpi=400)

# BASE_DIR = '/Users/nmndeep/Documents/logs_semseg/'

# worse_comp = [ 'WORST_CASE_5iter_rob_mod_0.0157_n_it_100_pascalvoc_ConvNeXt-T_CVST_ROB.pt',
# 'WORST_CASE_5iter_rob_mod_0.0314_n_it_100_pascalvoc_ConvNeXt-T_CVST_ROB.pt', 
# 'WORST_CASE_5iter_rob_mod_0.0471_n_it_100_pascalvoc_ConvNeXt-T_CVST_ROB.pt', 'WORST_CASE_5iter_rob_mod_0.0627_n_it_100_pascalvoc_ConvNeXt-T_CVST_ROB.pt']

# if True:
#     out_str = worse_comp[0][:16] + worse_comp[0][-22:-3]
#     eps_ = ['4/255', '8/255', '12/255', '16/255']
#     liss = []


#     for i in range(len(worse_comp)):
#         vall = torch.load(BASE_DIR + f"worst_case_numbers/{worse_comp[i]}")
#         final_acc_ = vall['final_matrix'].min(0)[1].unique(return_counts=True)[1]
#         # #put cospgd at 1, js-avg at 3 and mask-ce at 4
#         # final_acc_[final_acc_ == 1] = 200
#         # final_acc_[final_acc_ == 3] = 201
#         # final_acc_[final_acc_ == 4] = 202
#         # final_acc_[final_acc_ == 200] = 4
#         # final_acc_[final_acc_ == 201] = 1
#         # final_acc_[final_acc_ == 202] = 3
#         liss.append(final_acc_.numpy()) 
# print(liss)

# liss = np.asarray(liss)
# data = np.transpose(liss)

# # fig = plt.figure()
# # ax = fig.add_axes([0,0,1,1])
# # X = np.arange(4)
# # ax.bar(X + 0.16, data[0], color = my_cmap(1), width = 0.16)
# # ax.bar(X + 0.33, data[1], color = my_cmap(3), width = 0.16)
# # ax.bar(X + 0.50, data[2], color = my_cmap(5), width = 0.16)
# # ax.bar(X + 0.67, data[3], color = my_cmap(7), width = 0.16)
# # ax.bar(X + 0.84, data[4], color = my_cmap(9), width = 0.16)
# # ax.bar(X + 1.0,  data[-1], color = my_cmap(11), width = 0.16)



# yy = data
# losses_lis = ['CE-avg','Mask-CE-avg', 'SegPGD','CosPGD', 'JS-avg', 'Mask-$\ell_2$-norm']


# total_width = 0.5 # 0 ≤ total_width ≤ 1
# d = 0.01 # gap between bars, as a fraction of the bar width
# width = total_width/(len(data[0])+(len(data[0])-1)*d)
# offset = -total_width/6

# ### plot    
# x = np.arange(4)
# fig = plt.figure(figsize=(12, 8))
# ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])
# i=0
# ticks = []
# for idx, mod in enumerate(range(6)):
#     plt.bar(x+offset, yy[idx], width, align='center', label=losses_lis[idx], color=my_cmap4(int(idx*2)+1), hatch="/" if idx in [1,4,5] else None)
#     # else:
#     # print(yy[idx])
#     #   ax.bar(x+offset, yy[idx], width, align='center', label=mod, color=my_cmap2(idx+1))
#     ticks.append((x+offset))
#     offset += (1+d)*width
# # print(ticks)
# tks = np.arange(0, 4.43, 1.11)
# tks[0]+=.15
# tks[1]+=.11
# ax.set_xticks(tks)
# ax.set_xticklabels(eps_, fontsize=28)
# # plt.ylabel()
# # minn = round_near_five(min([item for sublist in yy for item in sublist]))
# # maxx = round_near_five(max([item for sublist in yy for item in sublist]))
# # ax.set_ylim([minn-2.5, maxx+2.5])
# ax.set_yticklabels(np.arange(0, 800, 100), fontsize=28) 
# # ax.set_xticks(x) 
# ax.set_ylim([0, 800])
# # ax.legend(fontsize=30, ncol=6)
# ax.legend(bbox_to_anchor=(.87,1.02),
#           fancybox=True, shadow=False, fontsize=30)
# # ax.set_xticklabels(eps_)
# ax.set_ylabel('Number of images with lowest aAcc', fontsize=30)
# ax.set_xlabel('Perturbation strength',  fontsize=30)
# # ax.legend(title="$\ell_{\infty}$ robustness", title_fontsize=14)
# plt.show()
# # plt.savefig("")
exit()
