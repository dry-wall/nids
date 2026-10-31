"""Single source of truth for paths, features, seeds and operating-point policy."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "cic-ids2017"
PROCESSED_DIR = ROOT / "data" / "processed"
SAMPLES_DIR = ROOT / "data" / "samples"
ARTIFACTS = ROOT / "artifacts"
BUNDLE_DIR = ARTIFACTS / "model_bundle"
FIGURES_DIR = ARTIFACTS / "figures"
TABLES_DIR = ARTIFACTS / "tables"
KB_DIR = ARTIFACTS / "kb"

SEED = 42
MODEL_SEEDS = (42, 43, 44)          # mean ± std over these for every trained model
SPLIT = (0.70, 0.15, 0.15)          # train / val / test, stratified by attack family
TARGET_FPR = 0.01                   # operating point: benign FPR on validation must stay <= 1 %

# The 12 CICFlowMeter features the detector uses (identifier columns are never features).
FEATURES = [
    "Flow Duration", "Total Fwd Packets", "Total Backward Packets",
    "Total Length of Fwd Packets", "Total Length of Bwd Packets",
    "Flow Bytes/s", "Flow Packets/s", "Fwd Packet Length Mean",
    "Bwd Packet Length Mean", "SYN Flag Count", "ACK Flag Count",
    "Average Packet Size",
]
LABEL_COL = "Label"

# File -> capture day. Used for the temporal (unseen-family) leakage check.
DAY_OF_FILE = {
    "Monday-WorkingHours.pcap_ISCX.csv": "Monday",
    "Tuesday-WorkingHours.pcap_ISCX.csv": "Tuesday",
    "Wednesday-workingHours.pcap_ISCX.csv": "Wednesday",
    "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv": "Thursday",
    "Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv": "Thursday",
    "Friday-WorkingHours-Morning.pcap_ISCX.csv": "Friday",
    "Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv": "Friday",
    "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv": "Friday",
}
TEMPORAL_TRAIN_DAYS = ("Monday", "Tuesday", "Wednesday")
TEMPORAL_TEST_DAYS = ("Thursday", "Friday")

# Raw CIC-IDS2017 label -> attack family (used for reporting only; the Phase-1 model is binary).
FAMILY_OF_LABEL = {
    "BENIGN": "Benign",
    "DoS Hulk": "DoS", "DoS GoldenEye": "DoS", "DoS slowloris": "DoS", "DoS Slowhttptest": "DoS",
    "DDoS": "DDoS",
    "PortScan": "PortScan",
    "FTP-Patator": "Brute Force", "SSH-Patator": "Brute Force",
    "Web Attack - Brute Force": "Web Attack", "Web Attack - XSS": "Web Attack",
    "Web Attack - Sql Injection": "Web Attack",
    "Bot": "Bot",
    "Infiltration": "Infiltration",
    "Heartbleed": "Heartbleed",
}
