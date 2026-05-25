-- Seed AI01/AI02/AI03 — 3 GPU-VPS slots on bcseserver1 (192.168.2.98).
-- Each maps to a Linux user (research0N) with one RTX 6000 Ada pinned via
-- CUDA_VISIBLE_DEVICES + cgroup limits. Real SSH will work once backend admin
-- pubkey is installed on those users (see scripts/install_backend_key_on_vps.py
-- — parameterise for ssh_user once bcseserver1 is reachable on the LAN).
INSERT INTO devices
    (name, device_type, model, internal_ip, ssh_port, ssh_user, status, power_state, capabilities)
VALUES
    ('ai01', 'vps', 'GPU-VPS Ubuntu — 1x RTX 6000 Ada 48GB', '192.168.2.98', 22, 'research01', 'available', 'on',
     '{"os":"Ubuntu 24.04","vcpu":8,"ram_gb":16,"disk_gb":100,"gpu":"NVIDIA RTX 6000 Ada","vram_gb":48,"cuda":"12.4","tier":"gpu","gpu_index":0}'::jsonb),
    ('ai02', 'vps', 'GPU-VPS Ubuntu — 1x RTX 6000 Ada 48GB', '192.168.2.98', 22, 'research02', 'available', 'on',
     '{"os":"Ubuntu 24.04","vcpu":8,"ram_gb":16,"disk_gb":100,"gpu":"NVIDIA RTX 6000 Ada","vram_gb":48,"cuda":"12.4","tier":"gpu","gpu_index":1}'::jsonb),
    ('ai03', 'vps', 'GPU-VPS Ubuntu — 1x RTX 6000 Ada 48GB', '192.168.2.98', 22, 'research03', 'available', 'on',
     '{"os":"Ubuntu 24.04","vcpu":8,"ram_gb":16,"disk_gb":100,"gpu":"NVIDIA RTX 6000 Ada","vram_gb":48,"cuda":"12.4","tier":"gpu","gpu_index":2}'::jsonb)
ON CONFLICT (name) DO UPDATE SET
    ssh_user = EXCLUDED.ssh_user,
    internal_ip = EXCLUDED.internal_ip,
    model = EXCLUDED.model,
    capabilities = EXCLUDED.capabilities,
    status = EXCLUDED.status
;

SELECT name, ssh_user, internal_ip, status,
       capabilities->>'gpu' AS gpu,
       capabilities->>'vram_gb' AS vram_gb,
       capabilities->>'tier' AS tier
FROM devices WHERE name LIKE 'ai0%' ORDER BY name;
