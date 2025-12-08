# main.py
import newclid.proof_scout.scout_config as config
from newclid.proof_scout.scout_pipeline import PipelineManager

def main():
    # 初始化管线
    manager = PipelineManager()
    
    current_batch = 0
    
    while True:
        # 1. & 2. & 3. 处理一个 Batch (1000题)
        # 包括：筛选、探索、求解
        has_data = manager.process_next_batch(current_batch)
        
        if not has_data:
            break
            
        # 4. 回训筛选器 (利用本轮新产生的 Label)
        manager.retrain_filter()
        
        # 5. 定期回捞 (Retrospective Review)
        # 假设每 5 个 Batch，回头检查一下这 5 个 Batch 里被漏掉的题
        if (current_batch + 1) % config.RETROSPECT_INTERVAL == 0:
            # 计算要回查的批次号，例如当前是4(第5批)，回查 0,1,2,3,4
            start_batch = current_batch - config.RETROSPECT_INTERVAL + 1
            batches_to_review = list(range(start_batch, current_batch + 1))
            
            manager.retrospective_review(batches_to_review)
            
            # 回捞产生了新数据，再微调一次模型（可选）
            manager.retrain_filter()
            
        current_batch += 1

if __name__ == "__main__":
    main()