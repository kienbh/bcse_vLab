export type Locale = "vi" | "en";

const MESSAGES = {
  // navigation
  "nav.home": { vi: "Trang chủ", en: "Home" },
  "nav.devices": { vi: "Thiết bị", en: "Devices" },
  "nav.bookings": { vi: "Lịch đặt", en: "Bookings" },
  "nav.dashboard": { vi: "Bảng điều khiển", en: "Dashboard" },
  "nav.login": { vi: "Đăng nhập", en: "Sign in" },
  "nav.logout": { vi: "Đăng xuất", en: "Sign out" },

  // hero
  "hero.eyebrow": { vi: "VJU Hardware Lab Portal", en: "VJU Hardware Lab Portal" },
  "hero.title": {
    vi: "Truy cập kit thực hành từ Mỹ Đình",
    en: "Access hardware kits from My Dinh campus",
  },
  "hero.subtitle": {
    vi: "Đăng nhập, đặt lịch, kết nối SSH tới FPGA / Jetson / Raspberry Pi đặt tại Hòa Lạc.",
    en: "Sign in, book a slot, SSH into FPGAs / Jetsons / Pis hosted in Hoa Lac lab.",
  },
  "hero.cta.login": { vi: "Đăng nhập", en: "Sign in" },
  "hero.cta.devices": { vi: "Xem thiết bị", en: "Browse devices" },

  // how it works
  "how.title": { vi: "3 bước để bắt đầu", en: "3 steps to get started" },
  "how.step1.title": { vi: "Đăng nhập", en: "Sign in" },
  "how.step1.desc": {
    vi: "Dùng tài khoản VJU. Giảng viên đã gán quyền lớp cho bạn.",
    en: "Use your VJU account. Your lecturer assigned class permissions.",
  },
  "how.step2.title": { vi: "Đặt lịch", en: "Book a slot" },
  "how.step2.desc": {
    vi: "Chọn thiết bị, chọn khung giờ. Hệ thống tự kiểm tra quota + xung đột.",
    en: "Pick a device + a window. The system checks quota + conflicts.",
  },
  "how.step3.title": { vi: "Kết nối", en: "Connect" },
  "how.step3.desc": {
    vi: "Đến giờ, click Connect → terminal SSH mở ngay trong trình duyệt.",
    en: "When the slot starts, click Connect → an SSH terminal opens in the browser.",
  },

  // features
  "feat.fpga.title": { vi: "FPGA AMD Kria KV260", en: "FPGA AMD Kria KV260" },
  "feat.fpga.desc": {
    vi: "Zynq UltraScale+ MPSoC — chạy PetaLinux/Ubuntu, nạp bitstream qua xmutil.",
    en: "Zynq UltraScale+ MPSoC — runs PetaLinux/Ubuntu, loads bitstreams via xmutil.",
  },
  "feat.jetson.title": { vi: "NVIDIA Jetson", en: "NVIDIA Jetson" },
  "feat.jetson.desc": {
    vi: "GPU edge — JetPack Linux, CUDA / TensorRT cho AI inference.",
    en: "GPU edge — JetPack Linux, CUDA / TensorRT for AI inference.",
  },
  "feat.rpi.title": { vi: "Raspberry Pi", en: "Raspberry Pi" },
  "feat.rpi.desc": {
    vi: "Linux đa năng + GPIO — thử nghiệm sensor, IoT, embedded protocols.",
    en: "General Linux + GPIO — sensor experiments, IoT, embedded protocols.",
  },

  // pages
  "page.devices.title": { vi: "Thiết bị", en: "Devices" },
  "page.devices.empty.title": { vi: "Chưa có thiết bị phù hợp", en: "No matching devices" },
  "page.devices.empty.desc": {
    vi: "Liên hệ giảng viên để được cấp quyền lớp, hoặc thay đổi bộ lọc.",
    en: "Contact your lecturer for class access, or change the filters.",
  },
  "page.bookings.title": { vi: "Lịch đặt của tôi", en: "My bookings" },
  "page.bookings.empty.title": { vi: "Chưa có lịch đặt", en: "No bookings yet" },
  "page.bookings.empty.desc": {
    vi: "Vào tab Thiết bị, chọn một kit và đặt slot đầu tiên.",
    en: "Go to Devices, pick a kit and book your first slot.",
  },
  "page.dashboard.title": { vi: "Bảng điều khiển", en: "Dashboard" },
  "page.dashboard.welcome": { vi: "Xin chào", en: "Welcome" },

  // dashboard cards
  "card.bookings.title": { vi: "Lịch sắp tới", en: "Upcoming bookings" },
  "card.bookings.cta": { vi: "Xem tất cả →", en: "See all →" },
  "card.actions.title": { vi: "Hành động nhanh", en: "Quick actions" },
  "card.actions.book": { vi: "Đặt thiết bị", en: "Book a device" },
  "card.actions.special": { vi: "Quyền đặc biệt", en: "Special access" },
  "card.actions.contact": { vi: "Liên hệ giảng viên", en: "Contact lecturer" },
  "card.devices.title": { vi: "Thiết bị khả dụng", en: "Available devices" },
  "card.devices.cta": { vi: "Duyệt thiết bị →", en: "Browse devices →" },

  // statuses
  "status.healthy": { vi: "Sẵn sàng", en: "Healthy" },
  "status.starting": { vi: "Đang dùng", en: "In use" },
  "status.down": { vi: "Offline", en: "Offline" },

  // footer
  "footer.note": {
    vi: "© {year} VJU Hardware Lab Portal — Khoa BCSE, Đại học Việt Nhật.",
    en: "© {year} VJU Hardware Lab Portal — BCSE, Vietnam Japan University.",
  },
} as const;

export type MessageKey = keyof typeof MESSAGES;

export function t(
  locale: Locale,
  key: MessageKey,
  vars?: Record<string, string>,
): string {
  const entry = MESSAGES[key];
  let text: string = entry ? entry[locale] : key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.replaceAll(`{${k}}`, v);
    }
  }
  return text;
}
