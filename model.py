import torch
import torch.nn as nn
import timm

class SRMLayer(nn.Module):
    def __init__(self):
        super().__init__()
        f1 = torch.tensor([
            [ 0,  0,  0,  0,  0],
            [ 0, -1,  2, -1,  0],
            [ 0,  2, -4,  2,  0],
            [ 0, -1,  2, -1,  0],
            [ 0,  0,  0,  0,  0]
        ], dtype=torch.float32)
        f2 = torch.tensor([
            [-1,  2, -2,  2, -1],
            [ 2, -6,  8, -6,  2],
            [-2,  8,-12,  8, -2],
            [ 2, -6,  8, -6,  2],
            [-1,  2, -2,  2, -1]
        ], dtype=torch.float32)
        f3 = torch.tensor([
            [ 0,  0,  0,  0,  0],
            [ 0,  0,  0,  0,  0],
            [ 0,  1, -2,  1,  0],
            [ 0,  0,  0,  0,  0],
            [ 0,  0,  0,  0,  0]
        ], dtype=torch.float32)
        filters = torch.stack([f1, f2, f3]).unsqueeze(1)
        self.conv = nn.Conv2d(1, 3, kernel_size=5, padding=2, bias=False)
        self.conv.weight.data = filters
        self.conv.weight.requires_grad = False

    def forward(self, x):
        gray = 0.299*x[:,0:1] + 0.587*x[:,1:2] + 0.114*x[:,2:3]
        return self.conv(gray)

class HybridDeepfakeDetector(nn.Module):
    def __init__(self):
        super().__init__()
        self.spatial = timm.create_model(
            "efficientnet_b4", pretrained=False, num_classes=0)
        self.srm = SRMLayer()
        self.frequency = timm.create_model(
            "xception", pretrained=False, num_classes=0, in_chans=3)
        self.classifier = nn.Sequential(
            nn.Linear(3840, 256),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(256, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        spatial_features = self.spatial(x)
        noise_maps = self.srm(x)
        freq_features = self.frequency(noise_maps)
        combined = torch.cat([spatial_features, freq_features], dim=1)
        return self.classifier(combined)
