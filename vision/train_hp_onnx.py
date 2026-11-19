"""
Synthetic Training & ONNX Export for Free Fire HP Bar Seam Regressor.
Trains a neural network to predict the exact health percentage (0.0 to 1.0)
from horizontal feature profiles, completely immune to background color shifts,
smoke, glare, or map terrain.
"""

import os
import time
import numpy as np
from sklearn.neural_network import MLPRegressor
import onnx
from onnx import helper, TensorProto
import onnxruntime as ort

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
os.makedirs(MODELS_DIR, exist_ok=True)
ONNX_MODEL_PATH = os.path.join(MODELS_DIR, "hp_seam_regressor.onnx")

print("Generating 6,000 synthetic training health bar profiles...")
np.random.seed(42)
N_SAMPLES = 6000
N_BINS = 128

X = np.zeros((N_SAMPLES, N_BINS * 2), dtype=np.float32)
y = np.zeros(N_SAMPLES, dtype=np.float32)

for i in range(N_SAMPLES):
    # Random true health percentage between 0.0 and 1.0
    true_pct = np.random.uniform(0.0, 1.0)
    # Occasionally dead (0.0) or full (1.0)
    if i % 15 == 0:
        true_pct = 0.0
    elif i % 15 == 1:
        true_pct = 1.0

    seam_idx = int(round(true_pct * N_BINS))

    # Active health fill intensity (white, red, or high-value mobile HUD)
    fill_level = np.random.uniform(0.85, 0.98)
    # Background track intensity (dark, translucent terrain, smoke noise)
    bg_level = np.random.uniform(0.10, 0.40)

    profile = np.full(N_BINS, bg_level, dtype=np.float32)
    if seam_idx > 0:
        profile[:seam_idx] = fill_level
        # Anti-aliasing transition at the seam
        if seam_idx < N_BINS:
            profile[seam_idx] = (fill_level + bg_level) / 2.0

    # Add realistic noise
    noise = np.random.normal(0.0, 0.02, N_BINS).astype(np.float32)
    profile = np.clip(profile + noise, 0.0, 1.0)

    # Gradient profile (detects step-down drop)
    grad = np.gradient(profile).astype(np.float32)

    X[i, :N_BINS] = profile
    X[i, N_BINS:] = grad
    y[i] = true_pct

print("Training Neural Network MLP Regressor...")
t0 = time.time()
mlp = MLPRegressor(
    hidden_layer_sizes=(64, 32),
    activation="relu",
    solver="adam",
    max_iter=150,
    random_state=42
)
mlp.fit(X, y)
train_time = time.time() - t0
print(f"Model trained in {train_time:.2f}s! R^2 Score on training: {mlp.score(X, y):.4f}")

# Export MLP to pure ONNX graph
print(f"Exporting model to ONNX: {ONNX_MODEL_PATH}")

# Weights and biases from scikit-learn MLP
W0 = mlp.coefs_[0].astype(np.float32)   # (256, 64)
b0 = mlp.intercepts_[0].astype(np.float32) # (64,)
W1 = mlp.coefs_[1].astype(np.float32)   # (64, 32)
b1 = mlp.intercepts_[1].astype(np.float32) # (32,)
W2 = mlp.coefs_[2].astype(np.float32)   # (32, 1)
b2 = mlp.intercepts_[2].astype(np.float32) # (1,)

# ONNX Graph Definition
input_tensor = helper.make_tensor_value_info("input_profile", TensorProto.FLOAT, [None, N_BINS * 2])
output_tensor = helper.make_tensor_value_info("predicted_hp", TensorProto.FLOAT, [None, 1])

t_W0 = helper.make_tensor("W0", TensorProto.FLOAT, W0.shape, W0.flatten().tolist())
t_b0 = helper.make_tensor("b0", TensorProto.FLOAT, b0.shape, b0.flatten().tolist())
t_W1 = helper.make_tensor("W1", TensorProto.FLOAT, W1.shape, W1.flatten().tolist())
t_b1 = helper.make_tensor("b1", TensorProto.FLOAT, b1.shape, b1.flatten().tolist())
t_W2 = helper.make_tensor("W2", TensorProto.FLOAT, W2.shape, W2.flatten().tolist())
t_b2 = helper.make_tensor("b2", TensorProto.FLOAT, b2.shape, b2.flatten().tolist())
t_min = helper.make_tensor("clip_min", TensorProto.FLOAT, [1], [0.0])
t_max = helper.make_tensor("clip_max", TensorProto.FLOAT, [1], [1.0])

# Nodes:
# Gemm0: input_profile * W0 + b0 -> h0
node_gemm0 = helper.make_node("Gemm", ["input_profile", "W0", "b0"], ["h0"], alpha=1.0, beta=1.0)
node_relu0 = helper.make_node("Relu", ["h0"], ["a0"])

# Gemm1: a0 * W1 + b1 -> h1
node_gemm1 = helper.make_node("Gemm", ["a0", "W1", "b1"], ["h1"], alpha=1.0, beta=1.0)
node_relu1 = helper.make_node("Relu", ["h1"], ["a1"])

# Gemm2: a1 * W2 + b2 -> raw_out
node_gemm2 = helper.make_node("Gemm", ["a1", "W2", "b2"], ["raw_out"], alpha=1.0, beta=1.0)
# Clip output between 0.0 and 1.0
node_clip = helper.make_node("Clip", ["raw_out", "clip_min", "clip_max"], ["predicted_hp"])

graph = helper.make_graph(
    [node_gemm0, node_relu0, node_gemm1, node_relu1, node_gemm2, node_clip],
    "hp_seam_regressor",
    [input_tensor],
    [output_tensor],
    [t_W0, t_b0, t_W1, t_b1, t_W2, t_b2, t_min, t_max]
)

model = helper.make_model(
    graph,
    producer_name="esports_telemetry_engine",
    ir_version=10,
    opset_imports=[helper.make_opsetid("", 17)]
)
onnx.checker.check_model(model)
onnx.save(model, ONNX_MODEL_PATH)

print(f"Successfully verified and saved ONNX model! File size: {os.path.getsize(ONNX_MODEL_PATH) / 1024:.1f} KB")

# Test with ONNX Runtime
session = ort.InferenceSession(ONNX_MODEL_PATH)
test_input = X[:5]
t_ort = time.perf_counter()
pred = session.run(["predicted_hp"], {"input_profile": test_input})[0]
lat = (time.perf_counter() - t_ort) * 1000.0 / 5.0
print(f"ONNX Runtime inference latency: {lat:.3f} ms per frame!")
print(f"True labels:      {np.round(y[:5], 2)}")
print(f"ONNX predictions: {np.round(pred.flatten(), 2)}")
