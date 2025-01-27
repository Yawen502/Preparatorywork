
'Data Preprocessing'
import torch
import math
import numpy as np

# Device configuration
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print("Using device:", device)

# get index of currently selected device
print(torch.cuda.current_device()) # returns 0 in my case

# get number of GPUs available
print(torch.cuda.device_count()) # returns 1 in my case

# get the name of the device
print(torch.cuda.get_device_name(0)) # good old Tesla K80

def snake_scan(img):
    'Converts a 32x32 image to a 32x96 array with snake-like row ordering'
    if len(img.shape) != 3:
        raise ValueError('Input image must be a 3D array')
    
    channels, rows, cols = img.shape
    snake = np.zeros((rows, cols * channels), dtype=img.dtype)
    for r in range(rows):
        row_data = img[:, r, :].flatten()  # Flattening each row into a 1D array of 96 elements
        if r % 2 == 1:
            row_data = row_data[::-1]  # Reversing the order for alternate rows
        snake[r] = row_data
    return snake

def stride(input_data, stride):
    'turn [batch_size, sequence_length, input_size] into [batch_size, sequence_length*input_size/stride, input_size]'
    batch_size, sequence_length, input_size = input_data.shape
    # flatten the input data to put sequence and input size together
    input_data = input_data.reshape(batch_size, -1)
    # append zeros to make sure the last pixel can be fed as the first pixel of the next sequence
    n = input_size - (sequence_length*input_size)%stride

    input_data = input_data.cpu()
    input_data = input_data.numpy()
    input_data = np.append(input_data, np.zeros((batch_size, n)), axis=1)
    input_data = torch.tensor(input_data)
    #print(input_data.shape)
    output_data = torch.zeros(batch_size, sequence_length*input_size//stride, input_size)
    for i in range(sequence_length*input_size//stride):
        # if stride = input size, then the output data is the same as input data
        #print(i)

        output_data[:,i,:] = input_data[:,i*stride:i*stride+input_size]
        #print(output_data[batch,i,:])

    return output_data

from torchvision import datasets
from torchvision import transforms
from torchvision.transforms import ToTensor
from torchvision.transforms import Lambda

transform = transforms.Compose([
    ToTensor(),
    Lambda(lambda x: torch.tensor(snake_scan(x.numpy())))
])

train_data = datasets.MNIST(
    root = 'data',
    train = True,                         
    download = True,
    transform = transform     
)
test_data = datasets.MNIST(
    root = 'data', 
    train = False, 
    download = True,
    transform = transform
)



'Hyperparameters'
from torch import nn
import torch.nn.functional as F

input_size = 8
sequence_length = 28*28//input_size
hidden_size = 24
num_layers = 1
num_classes = 10
batch_size = 40
num_epochs = 10
learning_rate = 0.01
stride_number = 4

from torch.utils.data import DataLoader
loaders = {
    'train' : torch.utils.data.DataLoader(train_data, 
                                          batch_size=batch_size, 
                                          shuffle=True, 
                                          num_workers=0),
    
    'test'  : torch.utils.data.DataLoader(test_data, 
                                          batch_size=batch_size, 
                                          shuffle=False, 
                                          num_workers=0),
}
loaders
'''
for i, (images, labels) in enumerate(loaders['train']):
    images = images.reshape(-1, sequence_length, input_size).to(device)
    images = stride(images, stride_number).to(device)
    print(images.shape)
    print(labels.shape)
    print(len(loaders['train']))
    break
'''



'Model Definition'
class customGRUCell(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers):
        super(customGRUCell, self).__init__()
        self.hidden_size = hidden_size
    
        # Rest gate r_t 
        self.w_r = torch.nn.Parameter(torch.rand(self.hidden_size, self.hidden_size))
        self.p_r = torch.nn.Parameter(torch.rand(self.hidden_size, input_size))           
        self.b_r = torch.nn.Parameter(torch.rand(self.hidden_size, 1))   

        # Update gate z_t
        # Wz is defined in the forward function
        self.w_z = torch.nn.Parameter(torch.rand(self.hidden_size, self.hidden_size))
        self.p_z = torch.nn.Parameter(torch.rand(self.hidden_size, input_size))
        self.b_z = torch.nn.Parameter(torch.rand(self.hidden_size, 1))         

        # Firing rate, Scaling factor and time step initialization
        self.r_t = torch.zeros(1, self.hidden_size, dtype=torch.float32)

        # Nonlinear functions
        self.Sigmoid = nn.Sigmoid()
        self.Tanh = nn.Tanh()
        for name, param in self.named_parameters():
            nn.init.uniform_(param, a=-(1/math.sqrt(hidden_size)), b=(1/math.sqrt(hidden_size)))

    def forward(self, x):        
        if self.r_t.dim() == 3:           
            self.r_t = self.r_t[0]
        self.r_t = torch.transpose(self.r_t, 0, 1)
        self.z_t = self.Sigmoid(torch.matmul(self.w_z, self.r_t) + torch.matmul(self.p_z, x) + self.b_z)
        self.r_t = (1 - self.z_t) * self.r_t + self.z_t * self.Sigmoid(torch.matmul(self.w_r, self.r_t) + torch.matmul(self.p_r, x) + self.b_r)
        self.r_t = torch.transpose(self.r_t, 0, 1)                

class customGRU(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers, batch_first=True):
        super(customGRU, self).__init__()
        self.rnncell = customGRUCell(input_size, hidden_size, num_layers).to(device)
        self.batch_first = batch_first

    def forward(self, x):
        if self.batch_first == True:
            for n in range(x.size(1)):
                #print(x.shape)
                x_slice = torch.transpose(x[:,n,:], 0, 1)
                self.rnncell(x_slice)
        return self.rnncell.r_t             
            
class RNN(nn.Module):
    
    def __init__(self, input_size, hidden_size, num_layers, num_classes):
        super(RNN, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = customGRU(input_size, hidden_size, num_layers)
        self.fc = nn.Linear(hidden_size, 10)
        pass

    def forward(self, x):
        # Set initial hidden and cell states 
        self.lstm.rnncell.r_t = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(device) 
        #c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(device)
        # Passing in the input and hidden state into the model and  obtaining outputs
        out = self.lstm(x)  # out: tensor of shape (batch_size, seq_length, hidden_size)
        #Reshaping the outputs such that it can be fit into the fully connected layer
        out = self.fc(out)
        return out.squeeze(-1)
        
        pass                                    
pass
model = RNN(input_size, hidden_size, num_layers, num_classes).to(device)
print(model)
loss_func = nn.CrossEntropyLoss()

'Trajactory Tracking and Training'
from torch import optim
model_optimizer = optim.Adam(model.parameters(), lr = learning_rate)   

from torch.utils.data import DataLoader, Subset
from sklearn.model_selection import StratifiedShuffleSplit

def subset_loader(full_dataset, batch_size, subset_ratio=0.1):
    # Generate labels array to use in stratified split
    labels = []
    for _, label in full_dataset:
        labels.append(label)
    labels = np.array(labels)

    # Perform a stratified shuffle split
    sss = StratifiedShuffleSplit(n_splits=1, test_size=subset_ratio, random_state=0)
    for train_index, test_index in sss.split(np.zeros(len(labels)), labels):
        stratified_subset_indices = test_index

    # Create a Subset instance with the stratified subset indices
    stratified_subset = Subset(full_dataset, stratified_subset_indices)

    # Create DataLoader from the subset
    subset_loader = DataLoader(
        stratified_subset,
        batch_size=batch_size,
        shuffle=False  # No need to shuffle as we already have a random subset
    )

    return subset_loader
subtest = subset_loader(test_data, batch_size)

def evaluate_while_training(model, loaders):
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for images, labels in subtest:
            images = images.reshape(-1, sequence_length, input_size).to(device)
            images = stride(images, stride_number).to(device)
            labels = labels.to(device)
            outputs = model(images)
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

    return 100 * correct / total

def train(num_epochs, model, loaders, patience=2, min_delta=0.01):
    model.train()
    total_step = len(loaders['train'])
    train_acc = []
    best_acc = 0
    no_improve_epochs = 0

    for epoch in range(num_epochs):
        for i, (images, labels) in enumerate(loaders['train']):
            images = images.reshape(-1, sequence_length, input_size).to(device)
            images = stride(images, stride_number).to(device)
            labels = labels.to(device)
            model.train()
            # Forward pass
            outputs = model(images)
            loss = loss_func(outputs, labels)

            # Backward and optimize
            model_optimizer.zero_grad()
            loss.backward()
            model_optimizer.step()
            
            if (i+1) % 750 == 0:
                accuracy = evaluate_while_training(model, loaders)
                train_acc.append(accuracy)
                print('Epoch [{}/{}], Step [{}/{}], Training Accuracy: {:.2f}' 
                      .format(epoch + 1, num_epochs, i + 1, total_step, accuracy))

                # Check for improvement
                if accuracy - best_acc > min_delta:
                    best_acc = accuracy
                    no_improve_epochs = 0
                else:
                    no_improve_epochs += 1

                if no_improve_epochs >= patience:
                    print("No improvement in validation accuracy for {} epochs. Stopping training.".format(patience))
                    return train_acc

    return train_acc

train_acc = train(num_epochs, model, loaders)

'Testing Accuracy'
# Test the model
model.eval()
with torch.no_grad():
    total_loss = 0
    correct = 0
    total = 0
    for images, labels in loaders['test']:
        images = images.reshape(-1, sequence_length, input_size).to(device)
        images = stride(images, stride_number).to(device)
        labels = labels.to(device)
        outputs = model(images)
        _, predicted = torch.max(outputs.data, 1)
        total += labels.size(0)
        correct += (predicted ==labels).sum().item()

test_acc = 100 * correct / total
print('Accuracy of the model:{}%'.format(test_acc))
with open('result.csv', 'a') as f:
    f.write('01_simple_GRU with input size:{}, test accuracy:{}\n'.format(input_size, test_acc))




"""
Epoch [10/10], Step [400/500], Training Accuracy: 21.40
Epoch [10/10], Step [500/500], Training Accuracy: 22.50
Accuracy of the model:23.43%
Epoch [10/10], Step [400/500], Training Accuracy: 50.20
Epoch [10/10], Step [500/500], Training Accuracy: 48.40
Accuracy of the model:49.29%
"""

# stride length 4
# input length 4, Accuracy of the model:89.72%
# input length 8, Accuracy of the model:89.59%
# input length 12, Accuracy of the model:91.71% 