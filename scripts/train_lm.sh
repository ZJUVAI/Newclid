#!/bin/bash
export LOGLEVEL=WARNING

# Model directory - modify this as needed
model_dir="lm_sft"

PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
NPROC_PER_NODE=4 \
CUDA_VISIBLE_DEVICES=0,1,2,3 \
swift sft \
    --model Qwen/Qwen3-0.6B-Base \
    --dataset 'datasets/20260612/geometry_clauses10_samples10M.jsonl' \
    --split_dataset_ratio 0 \
    --columns '{"llm_input_renamed": "query", "llm_output_renamed": "response"}' \
    --system 'You are a helpful assistant.' \
    --max_length 2048 \
    --packing true \
    --padding_free true \
    --dataset_num_proc 32 \
    --dataloader_num_workers 4 \
    --train_type full \
    --torch_dtype bfloat16 \
    --deepspeed zero1 \
    --attn_impl flash_attn \
    --use_liger_kernel true \
    --num_train_epochs 1 \
    --warmup_ratio 0.1 \
    --per_device_train_batch_size 16 \
    --gradient_accumulation_steps 1 \
    --learning_rate 1e-4 \
    --weight_decay 0.1 \
    --adam_beta1 0.9 \
    --adam_beta2 0.999 \
    --save_steps 10000 \
    --logging_steps 500 \
    --output_dir models/$model_dir \
    --add_version false \
    --save_only_model true \
    --full_determinism true \
    # --resume_from_checkpoint models/$model_dir/checkpoint-10000 \
    # --resume_only_model true \
    # --truncation_strategy left \
    # --lr_scheduler_type cosine_with_min_lr \
    # --lr_scheduler_kwargs '{"min_lr_rate":0.1}' \
    # --use_chat_template false \
