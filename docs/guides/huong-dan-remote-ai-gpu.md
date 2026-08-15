# Hướng dẫn remote vào máy chủ AI GPU (slot ai01 / ai02 / ai03)

> Dành cho sinh viên đã được cấp quyền (grant) slot AI GPU trên vLab Portal.
> Cập nhật: 07/07/2026.

## 1. Tổng quan

Máy chủ AI của lab có 3 GPU RTX 6000 Ada (48 GB VRAM mỗi card). Mỗi slot trên portal tương ứng 1 tài khoản Linux và 1 GPU riêng:

| Slot trên portal | Tài khoản Linux | GPU |
|------------------|-----------------|-----|
| ai01 | `research01` | GPU 0 |
| ai02 | `research02` | GPU 1 |
| ai03 | `research03` | GPU 2 |

> ⚠️ **`ai01` chỉ là tên slot hiển thị trên portal — KHÔNG phải username.**
> Khi SSH luôn dùng tài khoản Linux ở cột giữa: `research01`, `research02`, `research03`.
> Gõ `ssh ai01@...` sẽ bị `Permission denied` dù password đúng.

Kết nối đi qua **2 chặng** (bạn không kết nối thẳng vào máy chủ):

```
Máy của bạn ──(1) ssh vlab@ssh.bcse-vju.com:2222──▶ Gateway ──(2)──▶ research0N@192.168.2.98
              mật khẩu SLOT (portal cấp khi grant)          mật khẩu USER (hiển thị trong portal)
```

**Bạn cần 2 mật khẩu**, đều lấy từ portal khi nhận grant:

1. **Mật khẩu slot** — hiện đúng 1 lần khi bạn nhận grant, dùng cho user `vlab` ở chặng gateway.
2. **Mật khẩu user kit** — hiện trong cửa sổ booking (dòng "mật khẩu Linux"), dùng cho `research0N` ở chặng trong.

## 2. Cách 1 — SSH nhanh bằng terminal

Đơn giản nhất, portal đã cho sẵn lệnh:

```bash
ssh -p 2222 vlab@ssh.bcse-vju.com
```

Nhập mật khẩu slot → gateway tự chuyển tiếp vào máy đích. Phù hợp khi chỉ cần chạy lệnh, không cần forward port hay VS Code.

## 3. Cách 2 — VS Code Remote SSH (khuyến nghị khi code)

### 3.1. Cấu hình SSH

Mở file `~/.ssh/config` (Windows: `C:\Users\<tên bạn>\.ssh\config`, tạo mới nếu chưa có) và thêm:

```ssh-config
Host bcse-gpu
    HostName 192.168.2.98
    User research01
    ProxyJump vlab@ssh.bcse-vju.com:2222
```

Đổi `research01` thành đúng tài khoản slot của bạn (xem bảng ở mục 1).

### 3.2. Kết nối

**Terminal:**

```bash
ssh bcse-gpu
```

**VS Code:** cài extension **Remote - SSH** → `F1` → gõ `Remote-SSH: Connect to Host...` → chọn `bcse-gpu`.

Cả hai trường hợp sẽ hỏi mật khẩu **2 lần, theo thứ tự**:

1. `vlab@ssh.bcse-vju.com` → mật khẩu **slot**
2. `research0N@192.168.2.98` → mật khẩu **user kit**

Lần đầu VS Code kết nối sẽ mất ~1 phút để cài VS Code Server lên máy chủ — bình thường.

### 3.3. Kiểm tra GPU

Mỗi slot được gán cứng 1 GPU qua biến `CUDA_VISIBLE_DEVICES` (đặt sẵn trong tài khoản). Sau khi vào được, kiểm tra:

```bash
echo $CUDA_VISIBLE_DEVICES        # in ra số GPU của slot bạn (0, 1 hoặc 2)
python3 -c "import torch; print(torch.cuda.device_count())"   # → 1
```

Lưu ý: `nvidia-smi` vẫn liệt kê cả 3 card (lệnh này bỏ qua `CUDA_VISIBLE_DEVICES`) — dùng nó để xem mức chiếm dụng VRAM, nhưng code CUDA/PyTorch/TensorFlow của bạn chỉ chạy được trên đúng GPU được gán. Đừng tự ý ghi đè `CUDA_VISIBLE_DEVICES` để lấn sang GPU của slot khác.

## 4. Forward port (Jupyter, TensorBoard, ...)

Ví dụ chạy Jupyter trên máy chủ port 8888, xem trên trình duyệt máy mình:

```bash
ssh -L 8888:localhost:8888 bcse-gpu
# trên máy chủ:  jupyter lab --no-browser --port 8888
# trên máy bạn:  mở http://localhost:8888
```

Với VS Code Remote thì không cần lệnh trên — tab **Ports** tự động forward.

⚠️ **Lưu ý quan trọng**: phải forward theo kiểu trên (qua Host `bcse-gpu`, tức chặng trong). Nếu forward trực tiếp ở chặng gateway (`ssh -p 2222 vlab@... -L ...`) sẽ bị chặn với lỗi `administratively prohibited` — gateway chỉ cho phép đi tới port 22 của các máy trong pool.

## 5. Copy file lên/xuống

```bash
# Máy bạn → máy chủ
scp -r ./du-lieu bcse-gpu:~/

# Máy chủ → máy bạn
scp bcse-gpu:~/ket-qua.zip ./

# Hoặc rsync (tiếp tục được khi đứt mạng)
rsync -avP ./dataset/ bcse-gpu:~/dataset/
```

Kéo-thả file trong VS Code Remote cũng hoạt động. File nén: `unzip`, `zip`, `tar` đều đã cài sẵn trên máy chủ.

## 6. Giới hạn của tài khoản

- **Không có quyền sudo** — đây là chủ đích, không phải lỗi. Cần cài package hệ thống (apt) → nhắn giảng viên cài giúp.
- Package Python thì bạn tự cài bình thường trong môi trường của mình: `python -m venv venv` hoặc `pip install --user ...` / conda.
- **Dung lượng**: dữ liệu để trong `$HOME`, hạn mức 300 GB mỗi tài khoản (portal có hiển thị mức dùng).
- Grant có thời hạn — hết hạn thì kết nối mới bị từ chối. Xem hạn trên portal.

## 7. Lỗi thường gặp

| Triệu chứng | Nguyên nhân & cách xử lý |
|-------------|--------------------------|
| `administratively prohibited: open failed` | Forward port ở chặng gateway. Dùng cấu hình ProxyJump ở mục 3 và forward qua Host `bcse-gpu` (mục 4). |
| `Permission denied` ở lần hỏi mật khẩu thứ 2 (nhập đúng vẫn từ chối) | Kiểm tra **username chặng trong**: phải là `research01`/`research02`/`research03`, **không phải** tên slot `ai01`/`ai02`/`ai03`. Xem lại dòng `User` trong `~/.ssh/config`. |
| Hỏi mật khẩu mà nhập đúng vẫn bị từ chối | Nhầm thứ tự 2 mật khẩu: lần 1 là mật khẩu **slot** (vlab), lần 2 mới là mật khẩu **user kit** (research0N). |
| `Permission denied` ngay lần 1 | Mật khẩu slot đã hết hạn hoặc gõ sai. Vào portal xem lại grant / xin cấp lại. |
| `sudo: ... incident will be reported` / hỏi password khi `sudo` | Tài khoản không có sudo (mục 6). Nhắn giảng viên nếu cần cài package hệ thống. |
| VS Code treo ở "Setting up SSH host" | Mạng chậm lần đầu tải VS Code Server. Đợi 1–2 phút; nếu vẫn treo, `F1` → `Remote-SSH: Kill VS Code Server on Host` rồi kết nối lại. |

## 8. Áp dụng cho VPS pool (sv21–sv33)

Cách kết nối giống hệt, chỉ khác 2 chỗ trong `~/.ssh/config`:

- `HostName` = IP nội bộ của VPS (portal hiển thị trong booking)
- `User` = `student`

```ssh-config
Host bcse-vps
    HostName <IP VPS trong portal>
    User student
    ProxyJump vlab@ssh.bcse-vju.com:2222
```
