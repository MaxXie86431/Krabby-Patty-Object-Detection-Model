# -*- coding: utf-8 -*-
"""Krabby Patty Detection Working Script

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1rOH1hyuow3yE8fDA3s6_FW0k0ydZcRLw
"""

import torch
torch.cuda.empty_cache()

import os

# Create necessary directories for the project
os.makedirs('/content/krabbypatty', exist_ok=True)
os.makedirs('/content/labels', exist_ok=True)
os.makedirs('/content/testvid', exist_ok=True)
os.makedirs('/content/detectionoutput', exist_ok=True)
os.makedirs('/content/ground_truth_dir', exist_ok=True)

print("Directories created successfully: ")
print("/content/krabbypatty - For training images")
print("/content/labels - For XML labels in Pascal VOC format")
print("/content/testvid - For test video clips")
print("/content/detectionoutput - For saving detection output")
print("/content/ground_truth_dir - For saving ground truths for mAP")

import cv2
import torch
from torchvision import models, transforms
from torch.utils.data import Dataset, DataLoader
import os
import numpy as np
from xml.etree import ElementTree as ET
from PIL import Image
from tqdm import tqdm  # Importing tqdm for progress bars
import xml.etree.ElementTree as ET

class KrabbyPattyDataset(Dataset):
    def __init__(self, images_folder, labels_folder, transform=None):
        self.images_folder = images_folder
        self.labels_folder = labels_folder
        self.transform = transform

        # Cleanup unmatched files
        self.cleanup_unmatched_files()

        # Load matched image files only
        self.image_files = [f for f in os.listdir(images_folder) if f.endswith('.png')]

    def cleanup_unmatched_files(self):
        image_files = set(f for f in os.listdir(self.images_folder) if f.endswith('.png'))
        label_files = set(f.replace('.xml', '.png') for f in os.listdir(self.labels_folder) if f.endswith('.xml'))

        # Identify unmatched images and labels
        unmatched_images = image_files - label_files
        unmatched_labels = label_files - image_files

        # Delete unmatched images
        for img in unmatched_images:
            img_path = os.path.join(self.images_folder, img)
            os.remove(img_path)
            print(f"Deleted unmatched image: {img_path}")

        # Delete unmatched labels
        for lbl in unmatched_labels:
            lbl_path = os.path.join(self.labels_folder, lbl.replace('.png', '.xml'))
            os.remove(lbl_path)
            print(f"Deleted unmatched label: {lbl_path}")

    def __len__(self):
        return len(self.image_files)

    def __getitem__(self, idx):
        img_name = self.image_files[idx]
        img_path = os.path.join(self.images_folder, img_name)
        label_path = os.path.join(self.labels_folder, img_name.replace('.png', '.xml'))

        image = Image.open(img_path).convert("RGB")
        boxes, labels = self.parse_xml(label_path)

        if self.transform:
            image = self.transform(image)

        target = {'boxes': boxes, 'labels': labels}
        return image, target

    def parse_xml(self, label_path):
        tree = ET.parse(label_path)
        root = tree.getroot()

        boxes = []
        labels = []

        for obj in root.iter('object'):
            name = obj.find('name').text
            if name == 'Krabby Patty':  # Filter only Krabby Patty objects
                bndbox = obj.find('bndbox')
                xmin = int(bndbox.find('xmin').text)
                ymin = int(bndbox.find('ymin').text)
                xmax = int(bndbox.find('xmax').text)
                ymax = int(bndbox.find('ymax').text)

                boxes.append([xmin, ymin, xmax, ymax])
                labels.append(1)  # Assign label '1' for Krabby Patty

        boxes = torch.as_tensor(boxes, dtype=torch.float32)
        labels = torch.tensor(labels, dtype=torch.int64)
        return boxes, labels

# Load a pre-trained Faster R-CNN model
model = models.detection.fasterrcnn_resnet50_fpn(pretrained=True)

# Replace the classification head with a single class (Krabby Patty)
in_features = model.roi_heads.box_predictor.cls_score.in_features
model.roi_heads.box_predictor = models.detection.faster_rcnn.FastRCNNPredictor(in_features, 2)  # 2 classes: background and Krabby Patty

# Set model to training mode
model.train()

# Define image transformations
transform = transforms.Compose([transforms.ToTensor()])

# Create dataset and dataloaders
images_folder = '/content/krabbypatty'
labels_folder = '/content/labels'
dataset = KrabbyPattyDataset(images_folder, labels_folder, transform)
dataloader = DataLoader(dataset, batch_size=4, shuffle=True, collate_fn=lambda x: tuple(zip(*x)))

# Set device for training
device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
model.to(device)

# Define the optimizer
params = [p for p in model.parameters() if p.requires_grad]
optimizer = torch.optim.SGD(params, lr=0.001, momentum=0.9, weight_decay=0.0005)

# Define the training loop with progress bar
num_epochs = 25
for epoch in range(num_epochs):
    epoch_loss = 0
    for images, targets in tqdm(dataloader, desc=f"Training Epoch {epoch+1}/{num_epochs}", unit="batch"):
        images = [image.to(device) for image in images]
        targets = [{k: v.to(device) for k, v in t.items()} for t in targets]

        # Zero the gradients
        optimizer.zero_grad()

        # Forward pass
        loss_dict = model(images, targets)
        losses = sum(loss for loss in loss_dict.values())

        # Backward pass and optimization
        losses.backward()
        optimizer.step()

        epoch_loss += losses.item()

    print(f'Epoch {epoch+1}/{num_epochs}, Loss: {epoch_loss / len(dataloader)}')

# Save the trained model
torch.save(model.state_dict(), '/content/kpmodel.pth')

import cv2
import torch
import numpy as np
from torchvision import transforms
from tqdm import tqdm
import os
from torchvision.models.detection import fasterrcnn_resnet50_fpn
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

# Define device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Paths
model_path = '/content/kpmodel.pth'  # Path to the trained model weights file
output_dir = '/content/detectionoutput'
test_video_path = '/content/testvid/Screen Recording 2024-11-14 at 2.21.46 PM.mov'

# Load the Faster R-CNN model architecture
model = fasterrcnn_resnet50_fpn(pretrained=True)

# Replace the classifier with a new one for two classes (background and Krabby Patty)
num_classes = 2  # 1 class (Krabby Patty) + background
in_features = model.roi_heads.box_predictor.cls_score.in_features
model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)

# Load the trained weights
model.load_state_dict(torch.load(model_path, map_location=device))
model.to(device)
model.eval()  # Set model to evaluation mode

# Set up video capture
cap = cv2.VideoCapture(test_video_path)
fps = cap.get(cv2.CAP_PROP_FPS)
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Create detection output directory if it doesn't exist
os.makedirs(output_dir, exist_ok=True)
output_video_path = os.path.join(output_dir, 'kpdetectionoutput.mp4')
fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Codec for .mp4 format
out = cv2.VideoWriter(output_video_path, fourcc, fps, (frame_width, frame_height))

# Define the image transformation for the input frames
transform = transforms.Compose([
    transforms.ToTensor(),
])

# Initialize the predictions list to store the predictions in the required format
predictions = []

# Process frames and run detection
with torch.no_grad():  # Disable gradient computation for detection
    pbar = tqdm(total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), desc="Detecting frames")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Convert frame to RGB and transform to tensor
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_tensor = transform(frame_rgb).unsqueeze(0).to(device)

        # Perform detection
        prediction = model(frame_tensor)

        # Extract boxes, labels, and scores
        boxes = prediction[0]['boxes'].cpu().numpy()
        labels = prediction[0]['labels'].cpu().numpy()
        scores = prediction[0]['scores'].cpu().numpy()

        # Filter predictions with scores above the threshold
        threshold = 0.5
        high_confidence_indices = scores > threshold
        boxes = boxes[high_confidence_indices]
        labels = labels[high_confidence_indices]
        scores = scores[high_confidence_indices]

        # Save predictions in the format suitable for mAP calculation
        frame_id = int(cap.get(cv2.CAP_PROP_POS_FRAMES))  # Get the current frame number

        for i in range(len(boxes)):
            prediction_dict = {
                "image_id": frame_id,  # Frame number as image ID
                "bbox": boxes[i].tolist(),  # Convert bbox to list for saving
                "score": scores[i].item(),  # Confidence score
                "category_id": int(labels[i])  # Category ID (1 for Krabby Patty)
            }
            predictions.append(prediction_dict)

        # Draw bounding boxes on the detected objects
        for box in boxes:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)  # Green box

        # Write the frame with bounding boxes to the output video
        out.write(frame)
        pbar.update(1)

    cap.release()
    out.release()
    pbar.close()

# Save the predictions to a file for later use in mAP calculation
np.save('/content/predictions.npy', predictions)

print(f"Detection complete. Output video saved at {output_video_path}")

import numpy as np
import xml.etree.ElementTree as ET

# Helper function to parse Pascal VOC ground truth annotations
def parse_ground_truth(ground_truth_file):
    tree = ET.parse(ground_truth_file)
    root = tree.getroot()
    ground_truths = []

    # Extract relevant information from the annotation (xmin, ymin, xmax, ymax)
    for obj in root.findall('object'):
        bndbox = obj.find('bndbox')
        xmin = float(bndbox.find('xmin').text)
        ymin = float(bndbox.find('ymin').text)
        xmax = float(bndbox.find('xmax').text)
        ymax = float(bndbox.find('ymax').text)
        ground_truths.append([xmin, ymin, xmax, ymax])

    return ground_truths

# Load predictions and ground truths
predictions = np.load('/content/predictions.npy', allow_pickle=True)
ground_truth_dir = '/content/ground_truth_dir'
frame_ids_with_annotations = []  # List to store frames with ground truth annotations

# Prepare ground truth data: map frame numbers to their corresponding annotations
ground_truths = {}  # Dictionary to store ground truths by frame_id
for i in range(1, 709):  # Assuming you have frame numbers from 1 to 708
    frame_file = f'{ground_truth_dir}/frame_{i:06d}.xml'
    try:
        ground_truths[i] = parse_ground_truth(frame_file)
        frame_ids_with_annotations.append(i)
    except FileNotFoundError:
        continue  # Skip frames without annotations

# Prepare predictions
image_ids = [pred['image_id'] for pred in predictions]

# Filter predictions that match frames with annotations
filtered_predictions = [pred for pred in predictions if pred['image_id'] in frame_ids_with_annotations]

# mAP Calculation
true_positives = 0
false_positives = 0
false_negatives = 0

# Set an IoU threshold (e.g., 0.4) for considering a match
iou_threshold = 0.4

def iou(box1, box2):
    # Calculate intersection over union (IoU) for two bounding boxes
    x1, y1, x2, y2 = box1
    x1p, y1p, x2p, y2p = box2

    xi1 = max(x1, x1p)
    yi1 = max(y1, y1p)
    xi2 = min(x2, x2p)
    yi2 = min(y2, y2p)

    intersection_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    box1_area = (x2 - x1) * (y2 - y1)
    box2_area = (x2p - x1p) * (y2p - y1p)

    union_area = box1_area + box2_area - intersection_area
    return intersection_area / union_area if union_area != 0 else 0

# Evaluate True Positives and False Positives
for pred in filtered_predictions:
    image_id = pred['image_id']
    pred_bbox = pred['bbox']
    pred_score = pred['score']

    if image_id in ground_truths:  # Only consider frames with annotations
        gt_bboxes = ground_truths[image_id]

        matched = False
        for gt_bbox in gt_bboxes:
            iou_score = iou(pred_bbox, gt_bbox)
            if iou_score >= iou_threshold:
                true_positives += 1
                matched = True
                break

        if not matched:
            false_positives += 1

# Calculate False Negatives (ground truth boxes that weren't matched)
false_negatives = sum(len(gt_bboxes) for gt_bboxes in ground_truths.values()) - true_positives

# Calculate precision, recall, and mAP
precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
mAP = precision  # You can average precision over all frames for more granular mAP calculation

# Output results
print(f'True Positives: {true_positives}')
print(f'False Positives: {false_positives}')
print(f'False Negatives: {false_negatives}')
print(f'Precision: {precision:.4f}')
print(f'Recall: {recall:.4f}')
print(f'mAP: {mAP:.4f}')