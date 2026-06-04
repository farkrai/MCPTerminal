# MCP Terminal Assistant — Evaluation Report

**Date:** 2026-05-13 21:20  
**Model:** qwen2.5:3b  
**Ablation:** fresh_run_qwen25_3b  
**Context window:** 0 turns  
**Confidence threshold:** 0.5  

---

## Summary Metrics

| Metric | Value | Target |
|--------|-------|--------|
| Tool Accuracy        | 31.0%   | > 85%  |
| Action Accuracy      | 31.0%   | > 75%  |
| Parse Failure Rate   | 3.3%   | < 10%  |
| Hallucination Rate   | 1.7%   | < 5%   |
| Mean Latency         | 787 ms  | < 3000 ms |
| P95 Latency          | 3012 ms  | < 6000 ms |
| Total Evaluated      | 60    | 60     |

---

## Per-Category Breakdown

| Category | Count | Tool Acc | Action Acc | Mean Latency |
|----------|-------|----------|------------|--------------|
| chaining     |     5 | 66.7%    | 66.7%      | 2063 ms        |
| file_ops     |    15 | 26.7%    | 26.7%      | 964 ms        |
| git_ops      |    15 | 33.3%    | 33.3%      | 564 ms        |
| system_ops   |    15 | 20.0%    | 20.0%      | 564 ms        |
| test_ops     |    10 | 40.0%    | 40.0%      | 553 ms        |

---

## Per-Difficulty Breakdown

| Difficulty | Count | Tool Acc | Action Acc |
|------------|-------|----------|------------|
| easy       |    29 | 31.0%    | 31.0%      |
| medium     |    20 | 30.0%    | 30.0%      |
| hard       |    11 | 33.3%    | 33.3%      |

---

## Latency Distribution

```
   514-1186   ms | ██████████████████████████████ 56
  1186-1859   ms |                                1
  1859-2532   ms |                                0
  2532-3205   ms |                                1
  3205-3878   ms |                                1
  3878-4551   ms |                                0
  4551-5224   ms |                                0
  5224-5897   ms |                                1
```

---

## Failed Cases (42 / 60)

### [WRONG] ID 1 — file_ops / easy
**Input:** list all files in the current directory  
**Expected:** `FileHandler.list`  
**Got:** `file_list.` (conf 1.00)  
**Latency:** 5897 ms  

### [WRONG] ID 2 — file_ops / easy
**Input:** show me what files are here  
**Expected:** `FileHandler.list`  
**Got:** `file_list.` (conf 0.90)  
**Latency:** 551 ms  

### [WRONG] ID 6 — file_ops / easy
**Input:** find all python files in the project  
**Expected:** `FileHandler.search`  
**Got:** `file_list.` (conf 1.00)  
**Latency:** 685 ms  

### [WRONG] ID 7 — file_ops / easy
**Input:** search for all .py files recursively  
**Expected:** `FileHandler.search`  
**Got:** `file_search.` (conf 1.00)  
**Latency:** 683 ms  

### [WRONG] ID 8 — file_ops / easy
**Input:** list files in the mcp_assistant folder  
**Expected:** `FileHandler.list`  
**Got:** `file_list.` (conf 1.00)  
**Latency:** 547 ms  

### [WRONG] ID 9 — file_ops / medium
**Input:** find all json files under eval_data  
**Expected:** `FileHandler.search`  
**Got:** `file_list.` (conf 0.90)  
**Latency:** 641 ms  

### [WRONG] ID 10 — file_ops / medium
**Input:** look for configuration files in the project  
**Expected:** `FileHandler.search`  
**Got:** `file_list.` (conf 0.90)  
**Latency:** 606 ms  

### [WRONG] ID 12 — file_ops / medium
**Input:** show me the audit logger code  
**Expected:** `FileHandler.read`  
**Got:** `unknown.` (conf 0.20)  
**Latency:** 544 ms  

### [WRONG] ID 13 — file_ops / medium
**Input:** find test files in the tests directory  
**Expected:** `FileHandler.search`  
**Got:** `file_search.` (conf 1.00)  
**Latency:** 713 ms  

### [WRONG] ID 14 — file_ops / hard
**Input:** search for python test files that test the schema  
**Expected:** `FileHandler.search`  
**Got:** `file_search.` (conf 0.90)  
**Latency:** 685 ms  

### [WRONG] ID 15 — file_ops / hard
**Input:** find all files related to the dispatcher in the mcp package  
**Expected:** `FileHandler.search`  
**Got:** `file_search.` (conf 0.90)  
**Latency:** 730 ms  

### [WRONG] ID 18 — git_ops / easy
**Input:** show me the git log  
**Expected:** `GitTool.log`  
**Got:** `git_log.` (conf 1.00)  
**Latency:** 541 ms  

### [WRONG] ID 19 — git_ops / easy
**Input:** show recent commits  
**Expected:** `GitTool.log`  
**Got:** `git_log.` (conf 0.90)  
**Latency:** 635 ms  

### [WRONG] ID 20 — git_ops / easy
**Input:** show last 5 commits  
**Expected:** `GitTool.log`  
**Got:** `git_log.` (conf 0.90)  
**Latency:** 619 ms  

### [WRONG] ID 21 — git_ops / easy
**Input:** what branches do I have  
**Expected:** `GitTool.branch_list`  
**Got:** `git_branch_list.` (conf 1.00)  
**Latency:** 559 ms  

### [WRONG] ID 22 — git_ops / easy
**Input:** list all git branches  
**Expected:** `GitTool.branch_list`  
**Got:** `git_branch_list.` (conf 1.00)  
**Latency:** 567 ms  

### [WRONG] ID 23 — git_ops / easy
**Input:** show the git diff  
**Expected:** `GitTool.diff`  
**Got:** `git_diff.` (conf 1.00)  
**Latency:** 556 ms  

### [WRONG] ID 27 — git_ops / medium
**Input:** show the last 10 commits in the log  
**Expected:** `GitTool.log`  
**Got:** `git_log.` (conf 1.00)  
**Latency:** 514 ms  

### [WRONG] ID 28 — git_ops / medium
**Input:** commit my changes with the message fix null pointer error  
**Expected:** `GitTool.commit`  
**Got:** `git_commit.` (conf 0.90)  
**Latency:** 676 ms  

### [WRONG] ID 29 — git_ops / hard
**Input:** switch to the main branch  
**Expected:** `GitTool.branch_switch`  
**Got:** `git_branch_switch.` (conf 1.00)  
**Latency:** 519 ms  

_... and 22 more (see JSON for full list)_

---

_Generated by MCP Terminal Assistant eval harness_