'''
examples/torch/FlipFlop.py
Written for Python 3.8.17 and Pytorch 2.0.1
@ Matt Golub, June 2023
Please direct correspondence to mgolub@cs.washington.edu
'''

import pdb
import matplotlib.pyplot as plt
import sys
import time
import numpy as np

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

PATH_TO_FIXED_POINT_FINDER = '../../'
sys.path.insert(0, PATH_TO_FIXED_POINT_FINDER)
from FixedPointFinderTorch import FixedPointFinderTorch as FixedPointFinder
from FixedPoints import FixedPoints

from integret_flipflop import FlipFlopData

class FlipFlopDataset(Dataset):

	def __init__(self, data, device='cpu'):
		'''
		Args:
			data:
				Numpy data dict as returned by FlipFlopData.generate_data()

		Returns:
			None.
		'''
		
		super().__init__()
		self.device = device
		self.data = data

	def __len__(self):
		''' Returns the total number of trials contained in the dataset.
		'''
		return self.data['inputs'].shape[0]
	
	def __getitem__(self, idx):
		''' 
		Args:
			idx: slice indices for indexing into the batch dimension of data 
			tensors.

		Returns:
			Dict of indexed torch.tensor objects, with key/value pairs 
			corresponding to those in self.data.

		'''
		
		inputs_bxtxd = torch.tensor(
			self.data['inputs'][idx], 
			device=self.device)

		targets_bxtxd = torch.tensor(
			self.data['targets'][idx], 
			device=self.device)

		return {
			'inputs': inputs_bxtxd, 
			'targets': targets_bxtxd
			}

class FlipFlop(nn.Module):
	def __init__(self, input_size, hidden_size, num_classes):
		super(FlipFlop, self).__init__()
		self.hidden_size = hidden_size
		self.device = self._get_device()
		self.rnn = nn.RNN(input_size, hidden_size, batch_first=True).to(self._get_device())
		self.fc = nn.Linear(hidden_size, num_classes).to(self._get_device())
		self._loss_fn = nn.MSELoss().to(self._get_device())


	def forward(self, data):
		# Set initial hidden state
		x = data['inputs'].to(self.device)
		h0 = torch.zeros(1, x.size(0), self.hidden_size).to(self.device)

		# Forward pass through the RNN
		hidden, _ = self.rnn(x, h0)
		#print('hidden:', hidden.shape)
		
		# Pass the last hidden state through the fully connected layer
		out = self.fc(hidden)
		#print('out:', out.shape)
		return {
			'output': out, 
			'hidden': hidden,
			}
		
	def predict(self, data):
		''' Runs a forward pass through the model, starting with Numpy data and
		returning Numpy data.

		Args:
			data:
				Numpy data dict as returned by FlipFlopData.generate_data()

		Returns:
			dict matching that returned by forward(), but with all tensors as
			detached numpy arrays on cpu memory.

		'''
		dataset = FlipFlopDataset(data, device=self.device)
		pred_np = self._forward_np(dataset[:len(dataset)])
		# change keys to inputs and targets
		#pred_np['targets'] = pred_np.pop('output')
		return pred_np

	def _tensor2numpy(self, data):

		np_data = {}

		for key, val in data.items():
			np_data[key] = data[key].cpu().numpy()

		return np_data

	def _forward_np(self, data):

		with torch.no_grad():
			pred = self.forward(data)

		pred_np = self._tensor2numpy(pred)

		return pred_np

	def _loss(self, data, pred):

		return self._loss_fn(pred['output'], data['targets'])

	def train(self, train_data_gen, valid_data_gen, 
			learning_rate=1.0,
			batch_size=128,
			min_loss=1e-5, 
			disp_every=1, 
			plot_every=50, 
			max_norm=1.,
			regenerate_data_every_n_epochs=1,
			relative_error_threshold=1e-5):  # new argument for relative error threshold

		epoch = 0
		losses = []
		grad_norms = []
		mse_errors = []  # List to store MSE errors for plotting
		fig = None
		last_relative_error = float('inf')

		# Create the optimizer
		optimizer = optim.Adam(self.parameters(), 
			lr=learning_rate,
			eps=0.001,
			betas=(0.9, 0.999))

		scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
			optimizer, 
			mode='min',
			factor=.95,
			patience=1,
			cooldown=0)

		epoch = 0
		losses = []
		grad_norms = []
		fig = None
		
		while True:
			t_start = time.time()


			# Regenerate data at the beginning or at specified epochs
			if epoch % regenerate_data_every_n_epochs == 0:
				train_data = train_data_gen.generate_data(n_trials=4*batch_size)
				valid_data = valid_data_gen.generate_data(n_trials=batch_size)
				train_dataset = FlipFlopDataset(train_data, device=self.device)
				valid_dataset = FlipFlopDataset(valid_data, device=self.device)
			dataloader = DataLoader(train_dataset, 
									shuffle=True,
									batch_size=batch_size)

			if epoch % plot_every == 0:
				valid_pred = self._forward_np(valid_dataset[0:1])
				fig = FlipFlopData.plot_trials(valid_data, valid_pred, fig=fig)

			avg_loss, avg_norm = self._train_epoch(dataloader, optimizer)
			losses.append(avg_loss)
			grad_norms.append(avg_norm)

			scheduler.step(metrics=avg_loss)
			iter_learning_rate = scheduler.state_dict()['_last_lr'][0]

			# Calculate relative error
			valid_pred = self._forward_np(valid_dataset[:len(valid_dataset)])

			mse = self._loss_fn(torch.Tensor(valid_data['targets']), torch.Tensor(valid_pred['output']))
			mse_errors.append(mse)
			variance = np.var(valid_data['targets'], ddof=1)
			relative_error = mse / variance

			# Calculate change in relative error
			delta_relative_error = abs(relative_error - last_relative_error)

			# Check if change in relative error is below the threshold
			if delta_relative_error < relative_error_threshold:
				print(f'Stopping training. Change in relative error {delta_relative_error} is below threshold {relative_error_threshold}.')
				break

			last_relative_error = relative_error

			t_epoch = time.time() - t_start
					
			if epoch % disp_every == 0: 
				print('Epoch %d; Relative error: %.2e; Change in RE: %.2e; loss: %.2e; grad norm: %.2e; learning rate: %.2e; time: %.2es' %
					(epoch, relative_error, delta_relative_error, losses[-1], grad_norms[-1], iter_learning_rate, t_epoch))

			if avg_loss < min_loss or epoch > 1000:
				break

			epoch += 1

		# After training, plot the MSE trajectory
		#clear figures
		np.save('lent_workspace/easter02/fixed-point-finder/vanilla_mse_errors.npy', mse_errors)

		#valid_pred = self._forward_np(valid_dataset[0:1])
		#fig = FlipFlopData.plot_trials(valid_data, valid_pred, fig=fig)

		return losses, grad_norms

	def _train_epoch(self, dataloader, optimizer, verbose=False):

		n_trials = len(dataloader)
		avg_loss = 0; 
		avg_norm = 0

		for batch_idx, batch_data in enumerate(dataloader):

			step_summary = self._train_step(batch_data, optimizer)
			
			# Add to the running loss average
			avg_loss += step_summary['loss']/n_trials
			
			# Add to the running gradient norm average
			avg_norm += step_summary['grad_norm']/n_trials

			if verbose:
				print('\tStep %d; loss: %.2e; grad norm: %.2e; time: %.2es' %
					(batch_idx, 
					step_summary['loss'], 
					step_summary['grad_norm'], 
					step_summary['time']))

		return avg_loss, avg_norm

	def _train_step(self, batch_data, optimizer):
		'''
		Returns:

		'''

		t_start = time.time()


		# Run the model and compute loss
		batch_pred = self.forward(batch_data)
		loss = self._loss(batch_data, batch_pred)
		
		# Run the backward pass and gradient descent step
		optimizer.zero_grad()
		loss.backward()
		# nn.utils.clip_grad_norm_(model.parameters(), max_norm=max_norm)
		optimizer.step()

		grad_norms = [p.grad.norm().cpu() for p in self.parameters()]

		loss_np = loss.item()
		grad_norm_np = np.mean(grad_norms)

		t_step = time.time() - t_start

		summary = {
			'loss': loss_np,
			'grad_norm': grad_norm_np,
			'time': t_step
		}

		return summary

	@classmethod
	def _get_device(cls, verbose=False):
		"""
		Set the device. CUDA if available, else MPS if available (Apple Silicon), CPU otherwise.

		Args:
			None.

		Returns:
			Device string ("cuda", "mps" or "cpu").
		"""
		if torch.backends.cuda.is_built() and torch.cuda.is_available():
			device = "cuda"
			if verbose: 
				print("CUDA GPU enabled.")
		else:
			device = "cpu"
			if verbose:
				print("No GPU found. Running on CPU.")

		# I'm overriding here because of performance and correctness issues with 
		# Apple Silicon MPS: https://github.com/pytorch/pytorch/issues/94691
		#
		# elif torch.backends.mps.is_built() and torch.backends.mps.is_available():
		# 	device = "mps"
		# 	if verbose:
		# 		print("Apple Silicon GPU enabled.")

		return device
