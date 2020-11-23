import torch
import torch.nn as nn
import torch.nn.functional as F

import numpy as np
from itertools import combinations

class WeightedSum(nn.Module):
	'''
	'''
	def __init__(self, number_modals, stable, outchannels, trainable=False, mode=''):
		super(WeightedSum, self).__init__()
		self.NumberModalities = number_modals
		self.Mode = mode
		self.Stables = stable
		self.set_weights(outchannels, trainable)

	def set_weights(self, outchannels, trainable):
		'''
		'''
		w = list(range(0, self.NumberModalities))
		w_inputs = []
		for n in range(0,len(w) +1 -len(self.Stables)):
			for comb in combinations(w[len(self.Stables):], n):
				w_inputs.append(self.Stables + list(comb))
		self.WeightsAbi = w_inputs
		
		weights = []
		if self.Mode == 'convs':
			for i,ws in enumerate(w_inputs): ## review how well works
				setattr(self, 'Weight_%d'%(i),nn.Conv1d(len(ws), outchannels, kernel_size=1, stride=1))
				if not trainable:
					getattr(self, 'Weight_%d'%(i)).weight.requires_grad=False
		
		elif self.Mode == 'tensor':
			for i,ws in enumerate(w_inputs): ## review if works
				tt = torch.ones(len(ws), 1, dtype=torch.float)
				tt = torch.div(tt, torch.sum(tt, dim=0, keepdim=True))
				setattr(self, 'Weight_%d'%(i),nn.Parameter(tt, requires_grad=trainable))
		
		else:
			raise NameError('{} is not supported yet'.format(self.Mode))

	def forward(self, outs, availability):
		'''
		'''
		availability = torch.where(availability != 0)[0]
		for i, a in enumerate(self.WeightsAbi):
			a = torch.tensor(a)
			if a.shape != availability.shape:
					continue
			if torch.all(availability.eq(a)):
					ava_id = i
					break
		W = getattr(self,'Weight_%d'%(ava_id))#self.Weights[availability]
		if self.Mode == 'convs':
			out = W(outs)
		elif self.Mode == 'tensor': ### review how make it works as i like
			b, c, n = outs.shape
			out = torch.zeros(b, 1, n)
			for i, o in enumerate(outs):
				out[i,:,:] = (torch.mm(o.T, W)).T
		else:
			raise NameError('{} is not supported yet'.format(self.Mode))
		return out

class EmbraceNet(nn.Module):
	'''
	'''
	def __init__(self, input_size_list=[], embracement_size=32, docker_arch=[]):
		super(EmbraceNet, self).__init__()

		self.input_size_list = input_size_list
		self.embracement_size = embracement_size
		self.bypass_docking = self.set_dockers(docker_arch)

	def set_dockers(self, docker_architecture=[]):
		'''
			return boolean for use docking or not
		'''
		bypass = True
		for i, arch in enumerate(docker_architecture):
			bypass = False
			layers = []
			inC = self.input_size_list[i]
			for l in arch:
				if l == 'D':
					layers += [nn.Dropout()]
				elif l == 'R':
					layers += [nn.ReLU()]
				else:
					layers += [nn.Linear(inC,l)]
					inC = l
			setattr(self,'docking_%d' % (i),nn.Sequential(*layers))
		return bypass 

	def forward(self, input_list, availabilities=None, selection_probabilities=None):
		assert len(input_list) == len(self.input_size_list)
		num_modalities = len(input_list)
		batch_size = input_list[0].shape[0]

		docking_output_list = []
		if (self.bypass_docking):
			docking_output_list = input_list
		else:
			for i, input_data in enumerate(input_list):
				x = getattr(self, 'docking_%d' % (i))(input_data)## dockin must named docking_(i)
				x = nn.functional.relu(x)
				docking_output_list.append(x)
		
		if (availabilities is None):
			availabilities = torch.ones(batch_size, len(input_list), dtype=torch.float) #, device=self.device)
		else:
			availabilities = availabilities.float()
		
		if (selection_probabilities is None):
			selection_probabilities = torch.ones(batch_size, len(input_list), dtype=torch.float) #, device=self.device)
		selection_probabilities = torch.mul(selection_probabilities, availabilities)

		probability_sum = torch.sum(selection_probabilities, dim=-1, keepdim=True)
		selection_probabilities = torch.div(selection_probabilities, probability_sum)

		docking_output_stack = torch.stack(docking_output_list, dim=-1)  # [batch_size, embracement_size, num_modalities]

		modality_indices = torch.multinomial(selection_probabilities, num_samples=self.embracement_size, replacement=True)  # [batch_size, embracement_size]
		modality_toggles = nn.functional.one_hot(modality_indices, num_classes=num_modalities).float()  # [batch_size, embracement_size, num_modalities]

		embracement_output_stack = torch.mul(docking_output_stack, modality_toggles)
		embracement_output = torch.sum(embracement_output_stack, dim=-1)  # [batch_size, embracement_size]

		return embracement_output