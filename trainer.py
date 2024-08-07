import argparse
import torch.backends.cudnn as cudnn
from easydict import EasyDict as edict
from utils.ctools import TimeCounter
# from utils import tri18_model as model
# from utils import model 
from Res18 import lightMLP_model as model
from torch.utils.tensorboard import SummaryWriter
# from yolov10backbone import v10model
import cv2 
import yaml
import time
import torch.optim as optim
import torch.nn as nn
import torch
import numpy as np
import importlib
import os
import sys
from tqdm import tqdm 
sys.path.insert(0, os.getcwd())



def main(train):

    # Setup-----------------------------------------------------------
    dataloader = importlib.import_module(f"reader.{config.reader}")

    torch.cuda.set_device(config.device)

    attentionmap = cv2.imread(config.map, 0)/255
    attentionmap = torch.from_numpy(attentionmap).type(torch.FloatTensor)

    data = config.data
    save = config.save
    params = config.params

    # Prepare dataset-------------------------------------------------
    dataset = dataloader.loader(
        data, params.batch_size, shuffle=True, num_workers=4)

    # Build model
    # build model ------------------------------------------------
    print("===> Model building <===")
    # net = res18model.Model()
    
    # net = v10model.Model(alpha=1)
    net = model.Model()
    # net = v10model.Model(alpha=1)
    net.train()
    net.cuda()

    if config.pretrain:
        net.load_state_dict(torch.load(config.pretrain), strict=False)

    print("optimizer building")
    geloss_op = model.Gelossop(attentionmap, w1=3, w2=1)   # 修改了权重1：1 原来3：1
    deloss_op = model.Delossop()
    
    # 设置学习率为余弦调度
    
    ge_optimizer = optim.Adam(net.feature.parameters(),
                              lr=params.lr, betas=(0.9, 0.95))

    ga_optimizer = optim.Adam(net.gazeEs.parameters(),
                              lr=params.lr, betas=(0.9, 0.95))

    de_optimizer = optim.Adam(net.deconv.parameters(),
                              lr=params.lr, betas=(0.9, 0.95))
    # scheduler1 = optim.lr_scheduler.CosineAnnealingLR(ge_optimizer, T_max=5, eta_min=1e-5)
    # scheduler2 = optim.lr_scheduler.CosineAnnealingLR(ga_optimizer, T_max=5, eta_min=1e-5)
    # scheduler3 = optim.lr_scheduler.CosineAnnealingLR(de_optimizer, T_max=5, eta_min=1e-5)
    # scheduler = optim.lr_scheduler.StepLR(optimizer,
    # step_size=params.decay_step, gamma=params.decay)

    # prepare for training ------------------------------------

    length = len(dataset)
    total = length * params.epoch

    savepath = os.path.join(save.metapath, save.folder, f"checkpoint")

    if not os.path.exists(savepath):
        os.makedirs(savepath)

    timer = TimeCounter(total)

    print("Training")


    writer = SummaryWriter(log_dir=savepath)

    with open(os.path.join(savepath, "train_log"), 'w') as outfile:
        for epoch in range(1, config["params"]["epoch"]+1):
            for i, (data, label) in enumerate(tqdm(dataset)):

                # Acquire data
                data["face"] = data["face"].cuda()
                
                # output_folder ="./output"

                # os.makedirs(output_folder, exist_ok=True)
                # output_path = os.path.join(output_folder, f"epoch_{epoch}_iter_{i}.jpg")
                # image_numpy = data["face"][0].cpu().numpy().transpose(1, 2, 0)
                # #print(f"Transposed shape of image tensor: {image_numpy.shape}")

                # image_numpy = (image_numpy * 255).astype(np.uint8)
                # cv2.imwrite(output_path, image_numpy)   
                
                label = label.cuda()

                # forward
                gaze, img = net(data)

                ge_optimizer.zero_grad()
                ga_optimizer.zero_grad()
                de_optimizer.zero_grad()

                for param in net.deconv.parameters():
                    param.requires_grad = False

                # loss calculation
                geloss = geloss_op(gaze, img, label, data["face"])
                geloss.backward(retain_graph=True)

                for param in net.deconv.parameters():
                    param.requires_grad = True

                for param in net.feature.parameters():
                    param.requires_grad = False

                # for param in net.gazeEs.parameters():
                #     param.requires_grad = False

                deloss = deloss_op(img, data["face"])
                deloss.backward()

                for param in net.feature.parameters():
                    param.requires_grad = True

                    
                # for param in net.gazeEs.parameters():
                #     param.requires_grad = True
                    
                ge_optimizer.step()
                ga_optimizer.step()
                de_optimizer.step()

                # scheduler1.step()
                # scheduler2.step()
                # scheduler3.step()

                rest = timer.step()/3600

                # print logs
                if i % 20 == 0:
                    log = f"[{epoch}/{params.epoch}]: " + \
                          f"[{i}/{length}] " +\
                          f"gloss:{geloss} " +\
                          f"dloss:{deloss} " +\
                          f"lr:{params.lr} " +\
                          f"rest time:{rest:.2f}h"
                    writer.add_scalar("loss/gloss", geloss, epoch * length + i)
                    writer.add_scalar("loss/dloss", deloss, epoch * length + i)
                    # writer.add_scalar("lr", params.lr, epoch * length + i)
                    writer.add_scalar("rest time", rest, epoch * length + i)
                    # print(log)
                    outfile.write(log + "\n")
                    sys.stdout.flush()
                    outfile.flush()

            if epoch % config["save"]["step"] == 0:
                torch.save(net.state_dict(), os.path.join(
                    savepath, f"Iter_{epoch}_{save.name}.pt"))        
            

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Pytorch Basic Model Training')

    parser.add_argument('-c', '--config', type=str,
                        help='Path to the config file.')

    args = parser.parse_args()

    config = edict(yaml.load(open(args.config), Loader=yaml.FullLoader))

    main(config)
