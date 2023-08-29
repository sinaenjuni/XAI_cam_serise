import torch
from torchvision.transforms import Compose, Resize, ToTensor, Normalize
from datasets.cifar10 import CIFAR10
from torchsummary import summary
# from PIL import Image as pilimg
import matplotlib.pyplot as plt
import numpy as np
import cv2

class Cam(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.features = []
        self.weights = self.model.fc.weight # weigth shape is [classes, features]

        for module_name, module in self.model.named_modules():
            if isinstance(module, torch.nn.modules.pooling.AdaptiveAvgPool2d):
                module.register_forward_hook(self.hook)
            
    def hook(self, module, input, output):
        self.features.append(input[0])

    def forward(self, image):
        pred = self.model(image)
        _, target_index = torch.max(pred, 1)
        target_weight = self.weights[target_index.item()]

        # classifier weight * features
        heatmap = torch.mul(torch.squeeze(self.features[0]), target_weight.view(-1, 1, 1))
        heatmap = torch.sum(heatmap, axis=0)
        heatmap = heatmap.detach().cpu().numpy()
        heatmap = cv2.resize(heatmap, image_size, interpolation=cv2.INTER_CUBIC)

        # heatmap normalize [0~1]
        numer = heatmap - np.min(heatmap)
        denom = (heatmap.max() - heatmap.min()) + 1e-4
        heatmap = numer / denom
        heatmap = (heatmap * 255).astype("uint8")

        # https://docs.opencv.org/4.x/d3/d50/group__imgproc__colormap.html#gga9a805d8262bcbe273f16be9ea2055a65afdb81862da35ea4912a75f0e8f274aeb
        colormap = cv2.COLORMAP_VIRIDIS
        heatmap = cv2.applyColorMap(heatmap, colormap=colormap)
        return heatmap


if __name__ == "__main__":
    if torch.has_mps:
        device = torch.device("mps")

    data_path = "/Users/shinhyeonjun/code/class_activation_map/data/"
    batch_size = 32
    image_size = (256, 256)
    mean=(.5,.5,.5)
    std=(.5,.5,.5)
    transforms = Compose([ToTensor(), 
                          Resize(size=image_size, antialias=False), 
                          Normalize(mean=mean, std=std)])

    trainset = CIFAR10(root=data_path, train=True, download=True, transform=transforms, num_batchs=batch_size*2000)

    image = trainset[100][0][None,...]
    target = trainset[100][1]

    model = torch.load('./model.pt')
    model_weight = torch.load('./weights_12500.pt')['model_state_dict']
    model.load_state_dict(model_weight)
    model.eval()

    cam = Cam(model=model)
    heatmap = cam(image).to(device)

    vis_image = torch.squeeze(image).permute(1,2,0).numpy()
    vis_image = np.clip(255.0 * (vis_image * std + mean), 0, 255).astype(np.uint8)
    vis_image = cv2.cvtColor(vis_image, cv2.COLOR_RGB2BGR)

    alpha = 0.5
    output = cv2.addWeighted(vis_image, alpha, heatmap, 1 - alpha, 0)

    output = np.hstack([vis_image, heatmap, output])
    cv2.imshow("Output", output)
    cv2.waitKey(0)