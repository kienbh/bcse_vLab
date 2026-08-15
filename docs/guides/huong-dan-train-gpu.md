# Hướng dẫn nhanh: dùng GPU sau khi được cấp block

> Cho SV vừa được cấp block GPU. Copy data lên → train → lấy kết quả về.
> Cập nhật: 15/08/2026.

## 0. Chuẩn bị

- Đã đặt block và **đang trong giờ**.
- **2 mật khẩu, lấy từ portal** (đừng chép của bạn khác — có thể bị đổi định kỳ):
  1. *Mật khẩu slot* — bấm **"Get access"**, hiện 1 lần (cho user `vlab` ở cổng).
  2. *Mật khẩu user kit* — trong cửa sổ booking, dòng "mật khẩu Linux".

| Slot | Tài khoản Linux | GPU |
|------|-----------------|-----|
| ai01 | `research01` | 0 |
| ai02 | `research02` | 1 |
| ai03 | `research03` | 2 |

> ⚠️ `ai01/02/03` chỉ là tên slot — **username SSH là `research01`/`research02`/`research03`** tương ứng.

## 1. Cấu hình 1 lần

Thêm vào `~/.ssh/config` (Windows: `C:\Users\<tên>\.ssh\config`):

```ssh-config
Host gpu
    HostName 192.168.2.98
    User research01          # đổi theo slot của bạn
    ProxyJump vlab@ssh.bcse-vju.com:2222
```

## 2. Kết nối

```bash
ssh gpu
```

Hỏi mật khẩu **2 lần**: (1) slot → (2) user kit. VS Code: `F1` → *Remote-SSH: Connect to Host* → `gpu`.

Kiểm tra GPU: `nvidia-smi` • `echo $CUDA_VISIBLE_DEVICES`

## 3. Copy data LÊN (chạy trên máy bạn)

```bash
scp -r ./dataset gpu:~/                 # thư mục
rsync -avP ./dataset/ gpu:~/dataset/    # file lớn / mạng chập chờn
```

VS Code Remote: kéo-thả file vào cây thư mục bên trái. Quota **300 GB** trong `$HOME`.

**Hoặc `git clone` thẳng trên máy GPU** (nhanh hơn cho code/repo — máy GPU có internet):

```bash
# sau khi đã ssh gpu:
git clone https://github.com/<user>/<repo>.git
```

> Repo private: dùng token HTTPS, **đừng lưu token** lại trên máy dùng chung
> (xong việc: `git config --unset credential.helper`). Dataset lớn (>vài GB) thì
> dùng `rsync`/`wget` thay vì `git`.

## 4. Train (chạy trên máy GPU)

```bash
python3 -m venv ~/venv && source ~/venv/bin/activate
pip install -r requirements.txt

tmux new -s train          # chạy nền, thoát SSH không chết job
python train.py            # Ctrl+B rồi D để tách; quay lại: tmux attach -t train
```

Theo dõi: `watch -n 2 nvidia-smi`. Jupyter/TensorBoard: `ssh -L 8888:localhost:8888 gpu`.

## 5. Lấy kết quả RA (chạy trên máy bạn)

```bash
scp -r gpu:~/outputs ./outputs
rsync -avP gpu:~/outputs/ ./outputs/
```

VS Code: chuột phải → **Download**.

## 6. Lưu ý

- **Không sudo** (cố ý). Cần cài package hệ thống → nhắn giảng viên. Package Python tự cài trong venv.
- Data vẫn còn sau khi hết block, nhưng vẫn tính quota — dọn bằng `rm -rf ~/thu-muc-tam`.
- Hết block → SSH mới bị từ chối, phiên đang chạy bị cắt (cảnh báo trước 5 phút).

## 7. Lỗi hay gặp

| Lỗi | Xử lý |
|-----|-------|
| Từ chối mật khẩu lần 1 | Sai/hết hạn mật khẩu **slot** → bấm "Get access" lấy lại. |
| Từ chối lần 2 dù đúng | Sai username: phải `research0N`, không phải `ai0N`. |
| `administratively prohibited` khi scp | Phải dùng `gpu:~/...` (đã cấu hình ProxyJump), đừng trỏ thẳng cổng. |
| `No space left` | Hết quota 300 GB → `du -sh ~/*` tìm thư mục nặng rồi xóa. |
| `CUDA out of memory` | Giảm batch size, hoặc card đang bị chiếm (`nvidia-smi`). |
| Đóng SSH job chết | Chưa dùng `tmux`/`nohup` (mục 4). |

---

> **VPS thường (sv21–sv33)**: giống hệt, chỉ đổi `HostName` = IP trong booking và `User = student`.
