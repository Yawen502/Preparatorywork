'''
examples/torch/run_FlipFlop.py
Written for Python 3.8.17 and Pytorch 2.0.1
@ Matt Golub, June 2023
Please direct correspondence to mgolub@cs.washington.edu
'''

import pdb
import sys
import numpy as np

from FlipFlop_multiscale import FlipFlop
from FixedPointFinderTorch import FixedPointFinderTorch as FixedPointFinder
#from FlipFlopData import FlipFlopData
from integret_flipflop_nowindow import FlipFlopData
from plot_utils import plot_fps

def train_FlipFlop():
    ''' Train an RNN to solve the N-bit memory task.

        Args:
            None.

        Returns:
            model: FlipFlop object.

                The trained RNN model.

            valid_predictions: dict.

                The model's predictions on a set of held-out validation trials.
    '''

    # Data specifications
    n_bits = 2
    n_train = 512
    n_valid = 128

    # Model hyperparameters
    n_hidden = 100
    batch_size = 128

    # Instantiate FlipFlopData generators for training and validation
    train_data_gen = FlipFlopData(n_bits=n_bits)
    valid_data_gen = FlipFlopData(n_bits=n_bits)

    # Create an initial set of data for training and validation
    # This will be regenerated inside the train loop of the model
    initial_train_data = train_data_gen.generate_data(n_trials=n_train)
    initial_valid_data = valid_data_gen.generate_data(n_trials=n_valid)

    model = FlipFlop(
        input_size=n_bits,
        hidden_size=n_hidden,
        num_classes=n_bits)

    # Call the train method with the data generators
    losses, grad_norms = model.train(
        train_data_gen=train_data_gen,  # Passed the generator instead of data
        valid_data_gen=valid_data_gen,  # Passed the generator instead of data
        learning_rate=1./np.sqrt(batch_size),
        batch_size=batch_size,
        regenerate_data_every_n_epochs=10,
    )

    # After training, generate a final set of validation data to evaluate performance
    final_valid_data = valid_data_gen.generate_data(n_trials=n_valid)
    valid_predictions = model.predict(final_valid_data)

    return model, valid_predictions

def find_fixed_points(model, valid_predictions):
    ''' Find, analyze, and visualize the fixed points of the trained RNN.

    Args:
        model: FlipFlop object.

            Trained RNN model, as returned by train_FlipFlop().

        valid_predictions: dict.

            Model predictions on validation trials, as returned by
            train_FlipFlop().

    Returns:
        None.
    '''

    NOISE_SCALE = 0.5 # Standard deviation of noise added to initial states
    N_INITS = 2 # The number of initial states to provide
    print(valid_predictions.keys())
    n_bits = valid_predictions['output'].shape[2]

    '''Fixed point finder hyperparameters. See FixedPointFinder.py for detailed
    descriptions of available hyperparameters.'''
    fpf_hps = {
        'max_iters': 5,
        'lr_init': 1.,
        'outlier_distance_scale': 10.0,
        'verbose': True, 
        'super_verbose': True}

    # Setup the fixed point finder
    fpf = FixedPointFinder(model.rnn, **fpf_hps)

    '''Draw random, noise corrupted samples of those state trajectories
    to use as initial states for the fixed point optimizations.'''
    initial_states = fpf.sample_states(valid_predictions['hidden'],
        n_inits=N_INITS,
        noise_scale=NOISE_SCALE)

    # Study the system in the absence of input pulses (e.g., all inputs are 0)
    inputs = np.zeros([1, n_bits])

    # Run the fixed point finder
    unique_fps, all_fps = fpf.find_fixed_points(initial_states, inputs)

    # Visualize identified fixed points with overlaid RNN state trajectories
    # All visualized in the 3D PCA space fit the the example RNN states.
    fig = plot_fps(unique_fps, valid_predictions['hidden'],
        plot_batch_idx=list(range(30)),
        plot_start_time=10)

def main():
    # Step 1: Train an RNN to solve the N-bit memory task
    model, valid_predictions = train_FlipFlop()

    
    # STEP 2: Find, analyze, and visualize the fixed points of the trained RNN

    find_fixed_points(model, valid_predictions)

    print('Entering debug mode to allow interaction with objects and figures.')
    print('You should see a figure with:')
    print('\tMany blue lines approximately outlining a cube')
    print('\tStable fixed points (black dots) at corners of the cube')
    print('\tUnstable fixed points (red lines or crosses) '
        'on edges, surfaces and center of the cube')
    print('Enter q to quit.\n')
    pdb.set_trace()

if __name__ == '__main__':
    main()