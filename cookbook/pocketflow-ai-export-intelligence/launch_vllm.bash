CUDA_VISIBLE_DEVICES=4,5,6,7 nohup vllm serve meta-llama/Llama-3.3-70B-Instruct \
    --port 8001 \
    --api-key token01 \
    --download_dir /data02/shared/pferrazzi/.cache \
    --max-model-len 2048 \
    --tensor_parallel_size 4 \
    --enforce-eager &> nohup_vllm_llama70B