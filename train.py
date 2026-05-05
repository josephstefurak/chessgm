import csv
import os
import pickle
import random

import chess
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

from bot import get_best_move
from features import extract_features, FEATURE_NAMES

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CSV_PATH = os.path.join(DATA_DIR, "games.csv")
MODEL_PATH = os.path.join(DATA_DIR, "model.pkl")
NUM_GAMES = 300
MAX_MOVES = 150


def play_game(depth=2):
    board = chess.Board()
    positions = []

    for _ in range(MAX_MOVES):
        if board.is_game_over():
            break

        features = extract_features(board)
        positions.append(features)

        if board.fullmove_number <= 4 and random.random() < 0.5:
            move = random.choice(list(board.legal_moves))
        else:
            move = get_best_move(board, depth=depth)

        board.push(move)

    result = board.result()
    if result == "1-0":
        outcome = 1.0
    elif result == "0-1":
        outcome = -1.0
    else:
        outcome = 0.0

    return [(f, outcome) for f in positions]


def generate_data(num_games):
    all_data = []
    for i in range(num_games):
        print(f"Playing game {i + 1}/{num_games}...")
        game_data = play_game(depth=2)
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
    print("Training GradientBoostingRegressor...")
    model = GradientBoostingRegressor(n_estimators=200, max_depth=4, learning_rate=0.05)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    mse = mean_squared_error(y_test, preds)
    print(f"Test MSE: {mse:.4f}")
    print("Feature importances:")
    for name, imp in sorted(zip(FEATURE_NAMES, model.feature_importances_), key=lambda x: -x[1]):
        print(f"  {name}: {imp:.4f}")
    return model


def save_model(model):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    print(f"Model saved to {MODEL_PATH}")


if __name__ == "__main__":
    print(f"Generating {NUM_GAMES} self-play games at depth 2...")
    data = generate_data(NUM_GAMES)
    save_csv(data)
    print("\nTraining model...")
    X, y = load_csv()
    model = train_model(X, y)
    save_model(model)
    print("\nDone. Restart lichess-bot to use the new model.")