"""
Trains a small classifier (logistic regression) to replace the Tier 1
hand-tuned weighted sum in ConversationLinker, using the same
Slack-thread_ts-as-ground-truth approach as eval_conversation_linker.py.

For each Slack export given:
  - parse it, capture real reply_to (thread_ts-derived) pairs as ground truth
  - strip reply_to from every message
  - enumerate ALL candidate pairs ConversationLinker.iter_candidates would
    generate over the stripped data (not just ones that would clear a
    threshold) — each becomes one training row, labeled 1 if it matches a
    ground-truth pair and 0 otherwise

This is inherently a small-data problem: a chat export's thread_ts pairs are
the only labels available, and there are never many of them relative to the
number of candidate pairs the window generates (a heavily imbalanced
dataset — class_weight="balanced" compensates for that, not for having too
few positives overall). Pass more than one export to get a less noisy fit —
a single small export (like the bundled synthetic fixture) is enough to
prove the pipeline works end-to-end, not enough to trust the resulting
weights in production.

Usage:
    python Phase2/scripts/train_conversation_linker_classifier.py export1.zip export2.zip
    python Phase2/scripts/train_conversation_linker_classifier.py export.zip --output Phase2/models/custom.joblib
"""
import argparse
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.chat_parser import ChatParser
from src.conversation_linker import ConversationLinker, LinkerConfig, FEATURE_ORDER
from src.coref_resolver import get_embedding_texts
from src.llm_service import retrieval_service


def _unordered_pair(a: str, b: str) -> frozenset:
    return frozenset((a, b))


def _build_rows(slack_zip_path: str) -> Tuple[List[List[float]], List[int]]:
    messages = ChatParser.parse_slack(Path(slack_zip_path))
    ground_truth = {_unordered_pair(m.id, m.reply_to) for m in messages if m.reply_to}

    stripped = [m.model_copy(update={"reply_to": None}) for m in messages]
    embeddings = retrieval_service.generate_embeddings(get_embedding_texts(stripped))

    # scoring_mode is irrelevant here — we only read raw features off
    # iter_candidates and never call score_pairs, so this just drives the
    # window/decay settings the weighted_sum config also uses.
    linker = ConversationLinker(LinkerConfig.from_env())

    X, y = [], []
    for candidate in linker.iter_candidates(stripped, embeddings):
        pair = _unordered_pair(candidate.message_id_a, candidate.message_id_b)
        X.append([candidate.features[f] for f in FEATURE_ORDER])
        y.append(1 if pair in ground_truth else 0)

    return X, y


def train(slack_zip_paths: List[str], output_path: Path) -> None:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score, precision_score, recall_score
    import joblib

    all_X, all_y = [], []
    for path in slack_zip_paths:
        X, y = _build_rows(path)
        print(f"  {path}: {len(X)} candidate pairs, {sum(y)} positive")
        all_X.extend(X)
        all_y.extend(y)

    X = np.array(all_X)
    y = np.array(all_y)
    n_positive = int(y.sum())
    n_total = len(y)

    print(f"\nTotal training rows: {n_total} ({n_positive} positive, {n_total - n_positive} negative)")
    if n_positive < 20:
        print(
            f"CAUTION: only {n_positive} positive examples. A model fit on this few positives will\n"
            "overfit to this dataset's specific phrasing/timing and should be treated as a pipeline\n"
            "smoke test, not a trustworthy model — train on more/larger Slack exports before relying\n"
            "on classifier scoring mode in production."
        )

    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(X, y)

    y_pred = model.predict(X)
    precision = precision_score(y, y_pred, zero_division=0)
    recall = recall_score(y, y_pred, zero_division=0)
    f1 = f1_score(y, y_pred, zero_division=0)
    print(f"\nTrain-set fit (not held-out — see caution above): precision={precision:.3f} recall={recall:.3f} f1={f1:.3f}")

    print("\nLearned feature weights (higher = more this signal pushes toward 'linked'):")
    for name, coef in zip(FEATURE_ORDER, model.coef_[0]):
        print(f"  {name:12s} {coef:+.3f}")
    print(f"  {'intercept':12s} {model.intercept_[0]:+.3f}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_order": FEATURE_ORDER,
            "trained_on": slack_zip_paths,
            "n_samples": n_total,
            "n_positive": n_positive,
        },
        output_path,
    )
    print(f"\nSaved model to {output_path}")
    print(
        "Enable it with:\n"
        "  CONVERSATION_LINKING_SCORING_MODE=classifier "
        f"CONVERSATION_LINKING_MODEL_PATH={output_path}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slack_zips", nargs="+", help="One or more Slack export .zip paths")
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent.parent / "models" / "conversation_linker_classifier.joblib",
        help="Where to save the trained model (default: Phase2/models/conversation_linker_classifier.joblib)"
    )
    args = parser.parse_args()
    train(args.slack_zips, args.output)


if __name__ == "__main__":
    main()
