# Import necessary libraries

import numpy as np
import matplotlib.pyplot as plt
import os
import cv2
import itertools
from multiprocessing import Pool, cpu_count

from src.plot import plot_images


def unpickle(file):
    import pickle
    with open(file, 'rb') as fo:
        dict = pickle.load(fo, encoding='bytes')
    return dict

def load_and_preprocess_data(data_dir):
    car_images = []
    edge_images = []
    labels = []

    for batch in range(1, 6):
        file = os.path.join(data_dir, 'data_batch_' + str(batch))
        with open(file, 'rb') as fo:
            batch_data = unpickle(file)
            for i in range(len(batch_data[b'labels'])):
                if batch_data[b'labels'][i] == 1 or batch_data[b'labels'][i] == 9:  # labels for cars and trucks
                    image = np.reshape(batch_data[b'data'][i], (3, 32, 32)).transpose(1, 2, 0)
                    car_images.append(image)
                    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    edge_image = cv2.Canny(gray_image, 100, 200)
                    edge_images.append(edge_image)
                    labels.append(batch_data[b'labels'][i])

    # Convert to numpy arrays and return
    return np.array(car_images), np.array(edge_images), np.array(labels)


def extract_features_from_edge_image(edge_image):
    mean_intensity = np.mean(edge_image)
    white_pixel_count = np.sum(edge_image > 0)
    std_dev = np.std(edge_image)
    white_pixel_ratio = white_pixel_count / (edge_image.shape[0] * edge_image.shape[1])
    return [mean_intensity, white_pixel_count, std_dev, white_pixel_ratio]

class SOM:
    def __init__(self, input_dim, map_size, data, learning_rate=0.5, radius=1.0):
        self.input_dim = input_dim
        self.map_size = map_size
        self.learning_rate = learning_rate
        self.radius = radius
        self.weights = np.random.rand(map_size[0], map_size[1], self.input_dim)

    def _calculate_distance(self, x, y):
        return np.linalg.norm(x - y)

    def _find_winner(self, input_vector):
        distances = np.linalg.norm(self.weights - input_vector, axis=2)
        return np.unravel_index(distances.argmin(), distances.shape)

    def _update_weights(self, input_vector, winner_coords):
        # Calculate the distance from each neuron to the winner
        x = np.arange(self.map_size[0])
        y = np.arange(self.map_size[1])
        dist_x, dist_y = np.meshgrid(x, y)
        dist_to_winner = np.sqrt((dist_x - winner_coords[0]) ** 2 + (dist_y - winner_coords[1]) ** 2)

        # Only consider neurons within the given radius
        mask = dist_to_winner <= self.radius

        # Calculate the influence
        influence = np.exp(-dist_to_winner / (2 * (self.radius ** 2)))
        influence = influence * mask

        # Update weights for the influenced neurons
        delta = input_vector - self.weights
        for i in range(self.weights.shape[2]):
            self.weights[:, :, i] += self.learning_rate * influence * delta[:, :, i]

    def train(self, data, epochs):
        initial_lr = self.learning_rate
        initial_radius = self.radius
        for epoch in range(epochs):
            self.learning_rate = initial_lr * (1 - epoch / float(epochs))
            self.radius = initial_radius * (1 - epoch / float(epochs))
            for input_vector in data:
                winner_coords = self._find_winner(input_vector)
                self._update_weights(input_vector, winner_coords)


def visualize_som_clusters(cluster_centers, samples, ax):
    for center in cluster_centers:
        ax.scatter(center[0], center[1], color='black', s=100)

        # Find the distance to the nearest other cluster center to set the influence radius
        other_centers = [c for c in cluster_centers if not np.array_equal(c, center)]
        distances = [np.linalg.norm(center - c) for c in other_centers]
        influence_radius = min(distances) / 2
        circle = plt.Circle((center[0], center[1]), radius=influence_radius, color='red', fill=False)
        ax.add_artist(circle)

    # Plotting samples
    ax.scatter(samples[:, 0], samples[:, 1], color='blue', s=30, label='Punkt danych')

    ax.set_xlim([-1, cluster_centers[:, 0].max() + 2])
    ax.set_ylim([-1, cluster_centers[:, 1].max() + 2])
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.grid(True)
    ax.legend(loc='upper right')
    ax.grid(True)

def train_and_visualize(params):
    input_dim, map_size, feature_vectors, learning_rate, radius, epochs, output_directory = params
    som = SOM(input_dim=input_dim, map_size=map_size, data=feature_vectors, learning_rate=learning_rate, radius=radius)
    som.train(feature_vectors, epochs)

    # Extracting cluster centers from SOM weights
    cluster_centers = np.array([som.weights[i, j] for i in range(som.map_size[0]) for j in range(som.map_size[1])])
    samples_coords = np.array([som._find_winner(vec) for vec in feature_vectors])
    samples = np.array(
        [(coord[0] + np.random.normal(0, 0.2), coord[1] + np.random.normal(0, 0.2)) for coord in samples_coords])

    fig, ax = plt.subplots(figsize=(10, 10))
    visualize_som_clusters(cluster_centers, samples, ax)
    ax.set_title(f"Wspolczynnik uczenia: {learning_rate}, Promien: {radius}, Epoki: {epochs}", fontsize=12)

    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    filename = f"LR_{learning_rate}_Radius_{radius}_Epochs_{epochs}.png"
    filepath = os.path.join(output_directory, filename)
    plt.savefig(filepath)

    plt.close(fig)  # Close the figure after saving

def visualize_som_results(map_size, feature_vectors, learning_rates, radii, epochs_list, output_directory="result"):
    for lr in learning_rates:
        for r in radii:
            for ep in epochs_list:
                # Training the SOM
                som = SOM(input_dim=4, map_size=map_size, data=feature_vectors, learning_rate=lr, radius=r)
                som.train(feature_vectors, epochs=ep)

                # Extracting cluster centers from SOM weights
                cluster_centers = np.array(
                    [som.weights[i, j] for i in range(som.map_size[0]) for j in range(som.map_size[1])])

                # Mapping feature vectors to the SOM to get their coordinates
                samples_coords = np.array([som._find_winner(vec) for vec in feature_vectors])

                # Convert samples_coords with a smaller jitter
                samples = np.array(
                    [(coord[0] + np.random.normal(0, 0.03), coord[1] + np.random.normal(0, 0.03)) for coord in
                     samples_coords])

                # Plotting
                fig, ax = plt.subplots(figsize=(10, 10))
                # inny rodzaj graphow
                visualize_som_clusters(cluster_centers, samples, ax)
                ax.set_title(f"Wspolczynnik uczenia: {lr}, Promien: {r}, Epoki: {ep}", fontsize=12)

                # Adjusting visualization scale based on both samples and cluster centers
                all_points_x = np.concatenate([samples[:, 0], cluster_centers[:, 0]])
                all_points_y = np.concatenate([samples[:, 1], cluster_centers[:, 1]])
                ax.set_xlim([all_points_x.min() - 1, all_points_x.max() + 1])
                ax.set_ylim([all_points_y.min() - 1, all_points_y.max() + 1])

                # Save the plot to the directory
                filename = f"LR_{lr}_Promien_{r}_Epoki_{ep}.png"
                filepath = os.path.join(output_directory, filename)
                plt.savefig(filepath)

                plt.close(fig)

def main():
    data_dir = "cifar-10-batches-py"
    car_images, edge_images, _ = load_and_preprocess_data(data_dir)
    plot_images(car_images, edge_images)


def main_parallel():
    learning_rates = [0.01]
    radii = [1]
    epochs_list = [1]
    map_size = (20, 20)
    output_directory_edge = "result/test"

    # Load data
    data_dir = "cifar-10-batches-py"
    car_images, edge_images, _ = load_and_preprocess_data(data_dir)
    #edge images
    edge_feature_vectors = np.array([extract_features_from_edge_image(img) for img in edge_images])
    edge_feature_vectors = edge_feature_vectors - np.mean(edge_feature_vectors, axis=0)
    edge_feature_vectors = edge_feature_vectors / np.std(edge_feature_vectors, axis=0)


    # Get the number of available CPUs
    num_processes = cpu_count()

    with Pool(num_processes) as pool:
        edge_params = itertools.product([4],[map_size], [edge_feature_vectors], learning_rates, radii, epochs_list,
                                        [output_directory_edge])
        pool.map(train_and_visualize, edge_params)


if __name__ == "__main__":
    main_parallel()
