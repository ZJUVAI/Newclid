from __future__ import annotations

import unittest

import numpy as np

from newclid.agent.runtime.batched_decode import (
    decode_batched_continuations,
    strip_trailing_invalid_token_ids,
)


class BatchedDecodeTests(unittest.TestCase):
    def test_decode_batched_continuations_rebuilds_prefixed_outputs(self):
        requests = [
            {"request_id": "r0", "response_prefix": "<aux> x00", "new_point_name": "p"},
            {"request_id": "r1", "response_prefix": "<aux> x00", "new_point_name": "q"},
        ]
        model_inputs = {"input_ids": np.zeros((2, 8), dtype=np.int64)}
        sequences = [
            np.array([101, 102, 0, 0, 0, 0, 0, 0, 11, 12]),
            np.array([101, 102, 0, 0, 0, 0, 0, 0, 13, 14]),
            np.array([201, 202, 203, 0, 0, 0, 0, 0, 15, 16]),
            np.array([201, 202, 203, 0, 0, 0, 0, 0, 17, 18]),
        ]
        decoded = {
            (11, 12): " : perp b d c p [021] coll b d p [022] ; </aux>",
            (13, 14): " : cyclic a b c p [021] coll b d p [022] ; </aux>",
            (15, 16): " : perp a q b q [021] perp a q d q [022] ; </aux>",
            (17, 18): " : coll a b q [021] coll c d q [022] ; </aux>",
        }

        outputs = decode_batched_continuations(
            requests=requests,
            model_inputs=model_inputs,
            sequences=sequences,
            decoding_size=2,
            decode_batch=lambda batch: [
                decoded[tuple(item)] for item in batch
            ],
        )

        self.assertEqual(
            outputs,
            [
                [
                    "<aux> x00 p : perp b d c p [021] coll b d p [022] ; </aux>",
                    "<aux> x00 p : cyclic a b c p [021] coll b d p [022] ; </aux>",
                ],
                [
                    "<aux> x00 q : perp a q b q [021] perp a q d q [022] ; </aux>",
                    "<aux> x00 q : coll a b q [021] coll c d q [022] ; </aux>",
                ],
            ],
        )

    def test_decode_batched_continuations_uses_padded_input_width_not_per_sample_prompt_length(
        self,
    ):
        requests = [
            {"request_id": "r0", "response_prefix": "<aux> x00", "new_point_name": "p"}
        ]
        model_inputs = {"input_ids": np.zeros((1, 8), dtype=np.int64)}
        # The tokens before index 8 simulate left-padded prompt content; only
        # the continuation after index 8 should be decoded.
        sequences = [np.array([901, 902, 903, 904, 905, 906, 907, 908, 31, 32])]

        outputs = decode_batched_continuations(
            requests=requests,
            model_inputs=model_inputs,
            sequences=sequences,
            decoding_size=1,
            decode_batch=lambda batch: [
                " : perp b d c p [021] coll b d p [022] ; </aux>"
            ],
        )

        self.assertEqual(
            outputs,
            [["<aux> x00 p : perp b d c p [021] coll b d p [022] ; </aux>"]],
        )

    def test_decode_batched_continuations_preserves_beam_order(self):
        requests = [
            {"request_id": "r0", "response_prefix": "<aux> x00", "new_point_name": "p"}
        ]
        model_inputs = {"input_ids": np.zeros((1, 4), dtype=np.int64)}
        sequences = [
            np.array([0, 0, 0, 0, 41]),
            np.array([0, 0, 0, 0, 42]),
            np.array([0, 0, 0, 0, 43]),
        ]

        outputs = decode_batched_continuations(
            requests=requests,
            model_inputs=model_inputs,
            sequences=sequences,
            decoding_size=3,
            decode_batch=lambda batch: [
                f" : candidate_{item[0]} ; </aux>" for item in batch
            ],
        )

        self.assertEqual(
            outputs[0],
            [
                "<aux> x00 p : candidate_41 ; </aux>",
                "<aux> x00 p : candidate_42 ; </aux>",
                "<aux> x00 p : candidate_43 ; </aux>",
            ],
        )

    def test_decode_batched_continuations_preserves_nondefault_response_prefix(self):
        requests = [
            {
                "request_id": "r0",
                "response_prefix": "<aux> a x00",
                "new_point_name": "q",
            }
        ]
        model_inputs = {"input_ids": np.zeros((1, 4), dtype=np.int64)}
        sequences = [np.array([0, 0, 0, 0, 51, 52])]

        outputs = decode_batched_continuations(
            requests=requests,
            model_inputs=model_inputs,
            sequences=sequences,
            decoding_size=1,
            decode_batch=lambda batch: [" r : coll a b q [001] ; </aux>"],
        )

        self.assertEqual(
            outputs,
            [["<aux> a x00 q r : coll a b q [001] ; </aux>"]],
        )

    def test_strip_trailing_invalid_token_ids_strips_negative_sentinel(self):
        token_ids = [11, 12, 13, -1]
        self.assertEqual(
            strip_trailing_invalid_token_ids(token_ids),
            [11, 12, 13],
        )

    def test_decode_batched_continuations_strips_trailing_invalid_token(self):
        requests = [
            {"request_id": "r0", "response_prefix": "<aux> x00", "new_point_name": "p"}
        ]
        model_inputs = {"input_ids": np.zeros((1, 4), dtype=np.int64)}
        sequences = [np.array([0, 0, 0, 0, 61, 62, -1])]
        decoded = {
            (61, 62): " : coll a b p [001] ; </aux>",
        }

        outputs = decode_batched_continuations(
            requests=requests,
            model_inputs=model_inputs,
            sequences=sequences,
            decoding_size=1,
            decode_batch=lambda batch: [decoded[tuple(item)] for item in batch],
        )

        self.assertEqual(
            outputs,
            [["<aux> x00 p : coll a b p [001] ; </aux>"]],
        )


if __name__ == "__main__":
    unittest.main()
