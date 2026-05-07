"""
Neural network evaluator for chess positions.

Board encoding: 768 binary features
  - 64 squares × 6 piece types × 2 colors
  - 1.0 if that piece occupies that square, 0.0 otherwise
  - Index: square * 12 + (0 if White else 6) + piece_type_index

Network: 768 → 256 → 128 → 1
  - ReLU activations in hidden layers
  - Tanh output: bounded in (-1, 1)
  - Interpreted as game outcome: +1 = White wins, -1 = Black wins
  - Scaled to centipawns in evaluator.py

This replaces hand-crafted features with raw board representation,
letting the network discover patterns automatically from self-play data.
"""

import chess
import torch
import torch.nn as nn

BOARD_FEATURES = 768  # 64 squares × 6 piece types × 2 colors
PIECE_INDEX = {
    chess.PAWN: 0,
    chess.KNIGHT: 1,
    chess.BISHOP: 2,
    chess.ROOK: 3,
    chess.QUEEN: 4,
    chess.KING: 5,
}


def board_to_tensor(board):
    """
    Convert a chess board to a 768-dimensional binary tensor.
    Each feature is 1.0 if a specific piece occupies a specific square, else 0.0.
    Always encoded from White's perspective (White pieces first).
    """
    features = torch.zeros(BOARD_FEATURES)
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is not None:
            color_offset = 0 if piece.color == chess.WHITE else 6
            idx = sq * 12 + color_offset + PIECE_INDEX[piece.piece_type]
            features[idx] = 1.0
    return features


class ChessNet(nn.Module):
    """
    Small MLP that maps raw board position to expected game outcome.
    Output is in (-1, 1) via tanh:
      +1.0 = White wins
      -1.0 = Black wins
       0.0 = Draw
    """
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(BOARD_FEATURES, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Tanh(),
        )

    def forward(self, x):
        return self.net(x)


def load_model(path):
    """Load a trained ChessNet from disk. Returns None if file not found."""
    try:
        model = ChessNet()
        model.load_state_dict(torch.load(path, map_location="cpu"))
        model.eval()
        return model
    except FileNotFoundError:
        return None
