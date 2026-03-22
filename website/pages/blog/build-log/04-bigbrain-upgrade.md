# BigBrain Gets Smarter: Ollama 0.18, KV Cache Quantization, and Qwen 3.5

**Date:** March 2026
**Project:** AI Infrastructure
**Category:** Build Log
**Skills Demonstrated:** GPU memory optimization, LLM inference tuning, Proxmox VM resource management, Ollama configuration

---

## The Problem

BigBrain — our GPU-accelerated AI inference VM — was running Ollama 0.16.2 with Qwen 3 models on an RTX 4070 (12 GB VRAM). It worked, but we were hitting walls:

- **Context was expensive.** Every token of context ate into VRAM at full FP16 precision, limiting how much conversation history or document content the model could see at once.
- **VRAM was the bottleneck.** The 8B model ran comfortably, the 14B model fit with short contexts, and the 32B model required aggressive quantization with minimal context. We were leaving performance on the table.
- **Qwen 3 was already old.** Qwen 3.5 shipped in February 2026 with a fundamentally new architecture and significantly better benchmarks — especially for the agentic workflows our swarm depends on.

## What Changed

Three upgrades, applied in sequence:

### 1. VM Right-Sizing: 32 GB → 16 GB RAM

BigBrain was allocated 32 GB of system RAM but only using ~3.7 GB. The actual workload — Frigate (NVR with CUDA), n8n, and Caddy — is lightweight on system memory. The GPU VRAM (12 GB) is the real constraint for LLM inference, not system RAM.

Shrinking to 16 GB freed 16 GB on bighost, bringing available headroom from ~8 GB to ~24 GB for future agent swarm VMs. BigBrain still has 12 GB of breathing room above its actual usage.

```bash
qm set 102 --memory 16384
qm shutdown 102
qm start 102
```

### 2. Ollama 0.16.2 → 0.18.2 with KV Cache Quantization

The headline feature: **KV cache quantization**. When a model processes your prompt, it builds a key-value cache — essentially the model's working memory of the conversation. In Ollama 0.16, this cache used FP16 precision, consuming 2 bytes per value. At Q8_0, it uses 1 byte — halving the VRAM cost of context.

We enabled two environment variables via a systemd override:

```ini
[Service]
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
```

**Flash attention** reorganizes how the GPU computes attention scores, reducing memory overhead and improving throughput. **Q8_0 KV cache** quantizes the context cache from 16-bit to 8-bit with negligible quality loss (benchmarks show +0.002 to +0.05 perplexity — essentially nothing).

#### What This Means in Practice

For an 8B model on our 12 GB RTX 4070:

| Metric | Before (FP16 KV) | After (Q8_0 KV) |
|--------|-------------------|------------------|
| Model weights (Q4_K_M) | ~5.2 GB | ~5.2 GB |
| KV cache per 1K tokens | ~0.15 GB | ~0.08 GB |
| Available for context | ~6 GB | ~6 GB |
| Max context (approx) | ~40K tokens | ~75K tokens |

The model weights don't change — the savings are entirely in the context cache. For the 14B model, this is the difference between a tight 8K context and a comfortable 16K+. For the 32B model (which spills to system RAM), it reduces the GPU-resident portion of the cache, improving token generation speed.

### 3. Qwen 3 → Qwen 3.5

Qwen 3.5 isn't just a version bump — it's an architectural overhaul.

#### Hybrid Attention: The Big Idea

Qwen 3 used standard transformer attention, which scales quadratically with context length. Double the context, quadruple the compute. Qwen 3.5 introduces a **hybrid attention architecture** that alternates between two mechanisms in a 3:1 ratio:

- **Gated DeltaNet (3 of every 4 layers)** — A linear attention variant inspired by recurrent neural networks. Each layer compresses the input sequence into a fixed-size state, scaling near-linearly with context length instead of quadratically. This dramatically reduces KV cache memory for long sequences.
- **Full attention (1 of every 4 layers)** — Standard quadratic attention interspersed to maintain fine-grained token-to-token reasoning where it matters most.

The result: long-context processing is faster and cheaper. The 35B-A3B MoE variant can decode 256K-token contexts **19x faster** than Qwen 3's comparable model.

#### Benchmark Improvements

The gains are across the board, but the agentic improvements stand out:

| Benchmark | Qwen 3 (best comparable) | Qwen 3.5 | Improvement |
|-----------|--------------------------|-----------|-------------|
| Terminal-Bench 2.0 (agentic) | 22.5 | 52.5 | +133% |
| BrowseComp (agentic search) | — | 78.6 | New capability |
| GPQA Diamond (reasoning) | — | 81.7 (9B) | Beats models 3x its size |
| MMMU-Pro (visual reasoning) | — | 79.0 | Native multimodal |

The 9B model is particularly impressive — it outperforms the older Qwen 3-30B on key benchmarks including GPQA Diamond and IFEval, despite being a third of the size.

#### New Capabilities

- **Native multimodal** — text, image, and video processing through early fusion (vision support in Ollama is pending mmproj integration)
- **Multi-token prediction** — the model predicts several tokens per step, reducing costs by 10–60% across 201 languages
- **256K native context** — up from Qwen 3's 128K, and the hybrid attention makes it practical to actually use

### Optimal Model for 12 GB VRAM

With these upgrades, here's what fits on the RTX 4070:

| Model | Weights (Q4_K_M) | Max Context (Q8_0 KV) | Best For |
|-------|-------------------|------------------------|----------|
| **qwen3.5:9b** | ~6 GB | ~50K–75K tokens | Daily driver — strong reasoning, fast inference, room for long context |
| qwen3.5:4b | ~3 GB | ~100K+ tokens | Maximum context window, lighter tasks |
| qwen3.5:35b-a3b | ~22 GB (spills to RAM) | ~8K–16K on GPU | Highest quality, slower with CPU offload |
| qwen3.5:27b | ~17 GB (spills to RAM) | Limited on GPU | Dense model, not ideal for 12 GB |

**The sweet spot is qwen3.5:9b.** It fits entirely in VRAM at Q4_K_M with 6 GB to spare for context cache. With Q8_0 KV quantization, that translates to roughly 50K–75K tokens of context — enough for substantial document analysis or long multi-turn conversations. It outperforms Qwen 3-30B on reasoning benchmarks despite being a fraction of the size, and its hybrid attention architecture means long-context performance doesn't degrade the way it did with Qwen 3.

For the agent swarm, the **35b-a3b MoE variant** is worth watching. It activates only 3B parameters per token (meaning inference speed comparable to a 3B model) while drawing on 35B total parameters for quality. At Q4 quantization it needs ~22 GB, which spills to system RAM on our setup — but with 16 GB of system RAM available, it's usable for tasks where quality matters more than speed.

## The Result

BigBrain went from a capable but constrained inference server to one that punches well above its hardware class:

| | Before | After |
|---|--------|-------|
| Ollama | 0.16.2 | 0.18.2 |
| Model family | Qwen 3 | Qwen 3.5 |
| KV cache precision | FP16 | Q8_0 (half the VRAM) |
| Flash attention | Off | On |
| VM RAM | 32 GB (wasted) | 16 GB (right-sized) |
| Usable context (8B/9B) | ~40K tokens | ~75K tokens |
| Agentic benchmark | 22.5 | 52.5 (+133%) |
| Host headroom for new VMs | ~8 GB | ~24 GB |

The same $300 GPU now handles longer conversations, better reasoning, and stronger agentic capabilities — while freeing up resources on the host for the agent swarm infrastructure.

## What I Learned

- **VRAM budgeting is a balancing act** between model size, quantization, and context length. KV cache quantization shifts that balance significantly in your favor.
- **Right-size your VMs.** A 32 GB VM running 3.7 GB of workload is 28 GB of wasted capacity. Check actual usage before assuming you need what you allocated.
- **Architecture matters more than parameter count.** Qwen 3.5's 9B model beats Qwen 3's 30B model because hybrid attention and better training are more valuable than raw size.
- **MoE models change the math.** A 35B model that activates 3B parameters per token runs like a 3B model but thinks like a 35B model. On memory-constrained hardware, this is the future.

## Try It Yourself

**Minimum:** Any NVIDIA GPU with 8+ GB VRAM
**Software:** Ollama 0.17+ (for KV cache quantization), Qwen 3.5 models
**Time:** 15 minutes to upgrade and configure

```bash
# Upgrade Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Enable KV cache quantization (systemd override)
sudo mkdir -p /etc/systemd/system/ollama.service.d
cat <<EOF | sudo tee /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama

# Pull the new model
ollama pull qwen3.5:9b
```

---

*Built with Claude Code. Lab documented at rpc-cyberflight.com.*
