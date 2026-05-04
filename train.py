"""
Train the evaluator model via self-play.

Run this script standalone:
    python train.py

It will:
1. Play N games of bot vs bot
2. Record (features, outcome) for each position
3. Train a linear regression model
4. Save the model to data/model.pkl

After training, evaluator.py can load this model instead of using hardcoded material.
"""

import csv
import os
import pickle
import random

import chess
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

from bot import get_best_move
from features import extract_features, FEATURE_NAMES

DATA_DIR = "data"
CSV_PATH = os.path.join(DATA_DIR, "games.csv")
MODEL_PATH = os.path.join(DATA_DIR, "model.pkl")
NUM_GAMES = 50
MAX_MOVES = 150  # Cap game length to avoid infinite games


def play_game(depth=1):
    """
    Play one self-play game. Returns list of (features, outcome) tuples.
    Outcome is from White's perspective: 1 = White wins, -1 = Black wins, 0 = draw.
    """
    board = chess.Board()
    positions = []

    for _ in range(MAX_MOVES):
        if board.is_game_over():
            break

        features = extract_features(board)
        positions.append(features)

        # Add some randomness early in the game for variety
        if board.fullmove_number <= 4 and random.random() < 0.5:
            move = random.choice(list(board.legal_moves))
        else:
            move = get_best_move(board, depth=depth)

        board.push(move)

    # Determine outcome
    result = board.result()
    if result == "1-0":
        outcome = 1.0
    elif result == "0-1":
        outcome = -1.0
    else:
        outcome = 0.0  # Draw or unfinished (treat as draw)

    return [(f, outcome) for f in positions]


def generate_data(num_games):
    all_data = []
    for i in range(num_games):
        print(f"Playing game {i + 1}/{num_games}...")
        game_data = play_game(depth=1)
        all_data.extend(game_data)
    return all_data


def save_csv(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FEATURE_NAMES + ["outcome"])
        for features, outcome in data:
            writer.writerow(features + [outcome])
    print(f"Saved {len(data)} positions to {CSV_PATH}")


def load_csv():
    X, y = [], []
    with open(CSV_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            X.append([float(row[name]) for name in FEATURE_NAMES])
            y.append(float(row["outcome"]))
    return X, y


def train_model(X, y):
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = LinearRegression()
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    mse = mean_squared_error(y_test, preds)
    print(f"Test MSE: {mse:.4f}")
    print("Feature weights:")
    for name, coef in zip(FEATURE_NAMES, model.coef_):
        print(f"  {name}: {coef:.4f}")
    return model


def save_model(model):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    print(f"Model saved to {MODEL_PATH}")


if __name__ == "__main__":
    print(f"Generating {NUM_GAMES} self-play games...")
    data = generate_data(NUM_GAMES)
    save_csv(data)

    print("\nTraining model...")
    X, y = load_csv()
    model = train_model(X, y)
    save_model(model)
    print("\nDone. To use the trained model, update evaluator.py to load data/model.pkl.")
