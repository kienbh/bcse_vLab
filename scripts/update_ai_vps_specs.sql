-- Update AI01/02/03 specs to match verified bcseserver1 hardware (2026-05-27).
-- Host: AMD Ryzen Threadripper PRO 7975WX (64 threads), 251GB RAM, 1.8TB NVMe,
-- 3× RTX 6000 Ada (49140 MiB each). Per thầy 2026-05-27 spec:
-- 16 vCPU / 48GB / 300GB per VPS-GPU slot — leaves ~30% host for OS/admin/buffer.
UPDATE devices
SET capabilities = capabilities
    || jsonb_build_object(
        'vcpu', 16,
        'ram_gb', 48,
        'disk_gb', 300,
        'cuda', '12.x',
        'driver', '580.126.20',
        'host', 'bcseserver1 — Threadripper PRO 7975WX / 251GB RAM / 1.8TB NVMe',
        'gpu', 'NVIDIA RTX 6000 Ada',
        'vram_gb', 48,
        'tier', 'gpu'
    ),
    model = 'GPU-VPS Ubuntu 22.04 — 1× RTX 6000 Ada 48GB · 16 vCPU · 48GB RAM'
WHERE name IN ('ai01', 'ai02', 'ai03');

SELECT name, ssh_user, internal_ip, model,
       capabilities->>'vcpu' AS vcpu,
       capabilities->>'ram_gb' AS ram_gb,
       capabilities->>'disk_gb' AS disk_gb,
       capabilities->>'gpu' AS gpu,
       capabilities->>'vram_gb' AS vram_gb
FROM devices WHERE name LIKE 'ai0%' ORDER BY name;
