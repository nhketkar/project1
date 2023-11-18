import numpy as np
import sqlite3
import tensorflow as tf
from tensorflow.keras.preprocessing import image
from tensorflow.keras.applications.resnet50 import ResNet50, preprocess_input
from tensorflow.keras.layers import GlobalMaxPooling2D
from sklearn.neighbors import NearestNeighbors
from numpy.linalg import norm
import datetime

# Initialize the model
model = ResNet50(weights='imagenet', include_top=False, input_shape=(224, 224, 3))
model.trainable = False
model = tf.keras.Sequential([model, GlobalMaxPooling2D()])

def feature_extraction(img_path):
    """Extract features from an image."""
    img = image.load_img(img_path, target_size=(224, 224))
    img_array = image.img_to_array(img)
    expanded_img_array = np.expand_dims(img_array, axis=0)
    preprocessed_img = preprocess_input(expanded_img_array)
    result = model.predict(preprocessed_img).flatten()
    normalized_result = result / norm(result) if norm(result) > 0 else result
    return normalized_result

def get_embedding_and_image_paths(occasion, gender):
    """Retrieve file paths for embeddings, original images, and item IDs from the database based on occasion and gender."""
    conn = sqlite3.connect('your_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT file_path, image_path, item_id FROM embeddings WHERE occasion = ? AND Gender = ?', (occasion, gender))
    paths = cursor.fetchall()
    conn.close()
    return [(row[0], row[1], row[2]) for row in paths]

def load_occasion_data(occasion, gender):
    """Load embeddings, image paths, and item IDs for a given occasion and gender."""
    paths = get_embedding_and_image_paths(occasion, gender)
    feature_list = [np.load(embedding_path) for embedding_path, _, _ in paths]
    image_paths = [image_path for _, image_path, _ in paths]
    item_ids = [item_id for _, _, item_id in paths]
    return np.array(feature_list), image_paths, item_ids

def recommend(features, feature_list, image_paths, item_ids):
    """Recommend items based on features."""
    neighbors = NearestNeighbors(n_neighbors=5, algorithm='auto', metric='cosine')
    neighbors.fit(feature_list)
    distances, indices = neighbors.kneighbors([features])
    # Get the recommended image paths and item IDs
    recommended_image_paths = [image_paths[i].replace('\\', '/') for i in indices[0]]
    recommended_item_ids = [item_ids[i] for i in indices[0]]

    return recommended_image_paths, recommended_item_ids

def get_recommendations(img_path, occasion, gender):
    """Get recommendations for an image path based on occasion and gender."""
    features = feature_extraction(img_path)
    feature_list, image_paths, item_ids = load_occasion_data(occasion, gender)
    return recommend(features, feature_list, image_paths, item_ids)

def insert_recommendations(user_id, recommended_item_ids):
    """Insert recommendations into the database."""
    conn = sqlite3.connect('your_database.db')
    cursor = conn.cursor()

    try:
        for item_id in recommended_item_ids:
            timestamp = datetime.datetime.now()
            cursor.execute('''
                INSERT INTO recommendations (user_id, item_id, timestamp)
                VALUES (?, ?, ?)
            ''', (user_id, item_id, timestamp))
        conn.commit()
    except Exception as e:
        print("Database error: ", e)
    finally:
        conn.close()

