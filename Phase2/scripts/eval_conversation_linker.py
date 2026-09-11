"""
Evaluates the inferred-conversation-linking layer (src.conversation_linker)
using Slack's `thread_ts` as free ground truth.

Slack messages that already carry a real, parser-derived `reply_to` are the
only ground truth this project has for "these two messages are actually the
same thread" — WhatsApp exports have no equivalent to check against. So: take
a Slack export, strip `reply_to` from every message that has one, re-run the
Tier 1 scorer over the stripped data as if it had never been threaded, and
compare its guesses against the real threads it just had erased.

This is a manual eval tool, like `social_demo.py` — it loads the real
fastembed model and is not part of the automated pytest suite (see
tests/conftest.py, which stubs fastembed/yake out for that suite).

Usage:
    python Phase2/scripts/eval_conversation_linker.py path/to/slack_export.zip
    python Phase2/scripts/eval_conversation_linker.py path/to/slack_export.zip --threshold 0.4
    python Phase2/scripts/eval_conversation_linker.py path/to/slack_export.zip \\
        --scoring-mode classifier --model-path Phase2/models/conversation_linker_classifier.joblib
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.chat_parser import ChatParser
from src.conversation_linker import ConversationLinker, LinkerConfig
from src.coref_resolver import get_embedding_texts
from src.llm_service import retrieval_service


def _unordered_pair(a: str, b: str) -> frozenset:
    return frozenset((a, b))


def evaluate(slack_zip_path: str, threshold: float = None, scoring_mode: str = None, model_path: str = None) -> None:
    messages = ChatParser.parse_slack(Path(slack_zip_path))

    ground_truth = {
        _unordered_pair(msg.id, msg.reply_to)
        for msg in messages
        if msg.reply_to
    }

    if not ground_truth:
        print("No thread_ts-derived reply_to links found in this export — nothing to evaluate against.")
        return

    # Copies so the eval never mutates the messages it just extracted ground
    # truth from.
    stripped = [msg.model_copy(update={"reply_to": None}) for msg in messages]

    config = LinkerConfig.from_env()
    if threshold is not None:
        config.threshold = threshold
    if scoring_mode is not None:
        config.scoring_mode = scoring_mode
    if model_path is not None:
        config.model_path = model_path
    linker = ConversationLinker(config)

    embeddings = retrieval_service.generate_embeddings(get_embedding_texts(stripped))
    predicted_links = linker.score_pairs(stripped, embeddings)
    predicted = {_unordered_pair(link.message_id_a, link.message_id_b) for link in predicted_links}

    true_positives = predicted & ground_truth
    precision = len(true_positives) / len(predicted) if predicted else 0.0
    recall = len(true_positives) / len(ground_truth) if ground_truth else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    print(f"Scoring mode: {'classifier' if linker.using_classifier else 'weighted_sum'}")
    print(f"Ground-truth threaded pairs (thread_ts): {len(ground_truth)}")
    print(f"Predicted inferred links:                {len(predicted)}")
    print(f"True positives:                          {len(true_positives)}")
    print(f"Precision: {precision:.3f}")
    print(f"Recall:    {recall:.3f}")
    print(f"F1:        {f1:.3f}")
    if linker.using_classifier:
        print(f"(classifier_threshold={config.classifier_threshold}, model_path={config.model_path})")
    else:
        print(
            f"(config threshold={config.threshold}, weights sem/temp/turn/lex="
            f"{config.semantic_weight}/{config.temporal_weight}/"
            f"{config.turn_taking_weight}/{config.lexical_weight})"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slack_zip", help="Path to a Slack export .zip file")
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="Override CONVERSATION_LINKING_THRESHOLD for this run (weighted_sum mode only)"
    )
    parser.add_argument(
        "--scoring-mode", choices=["weighted_sum", "classifier"], default=None,
        help="Override CONVERSATION_LINKING_SCORING_MODE for this run"
    )
    parser.add_argument(
        "--model-path", default=None,
        help="Override CONVERSATION_LINKING_MODEL_PATH for this run (classifier mode only)"
    )
    args = parser.parse_args()
    evaluate(args.slack_zip, threshold=args.threshold, scoring_mode=args.scoring_mode, model_path=args.model_path)


if __name__ == "__main__":
    main()
