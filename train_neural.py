"""
Train the neural network evaluator via self-play.

Usage:
    python train_neural.py

Generates self-play games, encodes positions as 768-feature tensors,
trains ChessNet, saves to data/neural_model.pt.

After training, evaluator.py will automatically load and use this model.
The neural model replaces the sklearn model entirely — it takes raw board
position as input instead of hand-crafted features.

Recommended settings for a ~2 hour run:
    NUM_GAMES = 500
    SEARCH_DEPTH = 2
    EPOCHS = 30
"""

import os
import random
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split

import chess
from bot import get_best_move
from neural_net import ChessNet, board_to_tensor

NUM_GAMES = 500
SEARCH_DEPTH = 2
MAX_MOVES = 150
EPOCHS = 30
BATCH_SIZE = 512
LEARNING_RATE = 0.001

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MODEL_PATH = os.path.join(DATA_DIR, "neural_model.pt")


def play_game(depth=2):
    """
    Play one self-play game.
    Returns list of (tensor, outcome) pairs.
    Outcome: 1.0 = White wins, -1.0 = Black wins, 0.0 = draw.
    """
    board = chess.Board()
    positions = []

    for _ in range(MAX_MOVES):
        if board.is_game_over():
            break

        tensor = board_to_tensor(board)
        positions.append(tensor)

        # Random opening moves for variety
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

    return [(t, outcome) for t in positions]


def generate_data(num_games):
    all_tensors = []
    all_outcomes = []

    for i in range(num_games):
        print(f"Game {i + 1}/{num_games}...", end=" ", flush=True)
        game_data = play_game(depth=SEARCH_DEPTH)
        for tensor, outcome in game_data:
            all_tensors.append(tensor)
            all_outcomes.append(outcome)
        print(f"{len(game_data)} positions")

    X = torch.stack(all_tensors)
    y = torch.tensor(all_outcomes, dtype=torch.float32).unsqueeze(1)
    print(f"\nTotal positions: {len(X)}")
    return X, y


def train(X, y):
    # Train/val split
    n = len(X)
    split = int(0.9 * n)
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    train_ds = TensorDataset(X_train, y_train)
    val_ds = TensorDataset(X_val, y_val)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE)

    model = ChessNet()
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=0.5)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_state = None

    for epoch in range(1, EPOCHS + 1):
        # Training
        model.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(xb)
        train_loss /= len(X_train)

        # Validation
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for xb, yb in val_loader:
                pred = model(xb)
                val_loss += criterion(pred, yb).item() * len(xb)
        val_loss /= len(X_val)

        scheduler.step()

        print(f"Epoch {epoch:02d}/{EPOCHS}  train={train_loss:.4f}  val={val_loss:.4f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

    # Restore best weights
    model.load_state_dict(best_state)
    return model


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"Generating {NUM_GAMES} self-play games at depth {SEARCH_DEPTH}...")
    X, y = generate_data(NUM_GAMES)

    print("\nTraining neural network...")
    model = train(X, y)

    torch.save(model.state_dict(), MODEL_PATH)
    print(f"\nModel saved to {MODEL_PATH}")
    print("Restart lichess-bot to use the neural evaluator.")
