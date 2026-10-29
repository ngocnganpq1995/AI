# Stock News AI — Investor Workspace

Ứng dụng: https://stock-news-kngan.streamlit.app · GitHub: `1karenza/stock-news-ai`.

## Bốn tab

1. **I / Stock News**: quét tin theo danh sách mã, đọc tóm tắt và tiêu đề bài báo,
   mở nguồn, lưu tin và đánh dấu đã đọc.
2. **II / Lịch doanh nghiệp**: tự tải các mốc của mã cổ phiếu đang phân tích,
   gồm lịch sử cổ tức, quyền cổ đông, đại hội và thông báo doanh nghiệp.
   Ngày giao dịch không hưởng quyền, đăng ký cuối cùng, thực hiện và công bố
   được phân biệt; mặc định mở tháng gần nhất có dữ liệu.
3. **III / Giá cổ phiếu**: tự tải biểu đồ giá, khối lượng và cơ cấu sở hữu CafeF.
   Lịch cổ tức và phát hành được xem tại mục II, không lặp lại bên dưới mục III.
4. **IV / Định giá**: P/E, P/B, vốn hóa từ nguồn công khai; đối chiếu tối đa
   10 mã đối chiếu cùng mã nhóm ngành ngoài mã đang tra, ưu tiên vốn hóa lớn
   trong danh sách ngành nguồn trả về và tham chiếu tương đối.

Nhập mã ở thanh trái; chọn **Mã đang phân tích (II–IV)** và khoảng biểu đồ.
Các tab II–IV tự tải, không cần bấm quét. Tin ở tab I dùng **Quét và phân tích**.
Nút **Xuất report 4 tabs · PDF** ở thanh trái tải PDF trực tiếp, khổ A4 ngang,
có biểu đồ giá và biểu đồ tròn nhúng. Font tiếng Việt được đóng gói cùng app.
Bảng tin có 5 cột cân đối: ngày, mã, tóm tắt, tiêu đề, nguồn/loại tin;
không xuất hai cột đọc tin gốc và tình trạng nguồn. Không còn nút tải HTML.
Báo cáo ghi rõ phạm vi: tin đã quét cho danh sách mã, tab II–IV cho mã đang chọn.
Riêng mục II chỉ xuất sự kiện thuộc **Tháng có sự kiện** đang chọn trong lịch;
đổi tháng trước khi tải PDF để xuất đúng kỳ cần xem.

## Nguồn và giới hạn

- Tóm tắt chỉ lấy ý chính, tối đa 8 gạch đầu dòng, không có số ý tối thiểu.
  Lọc quảng cáo, hashtag và hướng dẫn website; không thêm ý cho đủ số lượng.
- Tiêu đề không được dùng thay cho tóm tắt. Bài tải rỗng hoặc quá ngắn không
  lưu vào cache xử lý, để lần quét sau có thể thử lại. Nguồn chặn truy cập,
  video hoặc trang chỉ có mô tả vẫn có thể chưa đủ nội dung để tóm tắt.
- Google News RSS và bài gốc cho tin tức; nếu bài gốc không đọc được, app chỉ
  sử dụng nội dung nguồn có sẵn, không tự tạo chi tiết.
- CafeF cho danh sách cổ đông, số cổ phiếu, tỷ lệ và ngày cập nhật từng công bố.
  Biểu đồ hai vòng từ API CoCauSoHuu của CafeF: vòng ngoài gồm cổ đông từ 1%
  và phần còn lại; vòng trong gồm nước ngoài/nhà nước/khác. Hai cách phân loại
  độc lập, không cộng chung. App và PDF dùng cùng biểu đồ vector.
- Simplize cho hồ sơ, quyền cổ đông và chỉ số định giá.
  Lịch sử giới hạn ở bản ghi nguồn trả về, tối đa 100 sự kiện quyền và các
  thông báo gần đây. Ngày công bố không thay thế ngày thực hiện; ngày đã qua
  không tự chứng minh sự kiện hoàn tất.
- Yahoo Finance (`<TICKER>.VN`) cho giá đóng cửa và khối lượng ngày, đơn vị VND.
  Chưa xác minh điều chỉnh chia tách; phiên đang giao dịch có thể chưa hoàn tất.
- Dữ liệu doanh nghiệp được cache 5 phút. Nút **Làm mới dữ liệu doanh nghiệp**
  cho phép thử tải lại. Nguồn lỗi hoặc thiếu được ghi rõ, không thay bằng số giả.
- P/E dùng TTM, P/B dùng quý gần nhất. Tham chiếu tương đối do app tính bằng
  EPS/BVPS nhân trung vị bội số của ít nhất hai mã hợp lệ, loại mã đang tra.
  Giá mục tiêu của tổ chức phân tích được trình bày riêng kèm ngày và nguồn.
  Dữ liệu không phải báo giá trực tiếp hay khuyến nghị đầu tư.

## Chạy và kiểm tra

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m streamlit run app.py
```

Cũng có thể mở `START_HERE_WINDOWS.bat`.
Các module cho bốn tab: `equity_data.py`, `equity_views.py`, `equity_pdf.py`,
cùng các module tin tức, hồ sơ và giá đã có. Cần commit đủ các file phụ thuộc.

## GitHub và triển khai

Repo `1karenza/stock-news-ai`, nhánh `main`, entry `app.py` tại root.
Streamlit Cloud tự redeploy sau khi push lên main. Lưu file local không tự push.

```powershell
git status
git diff
git add <cac-file-da-sua>
git diff --cached
git commit -m "Update dashboard"
git push origin main
```

Không commit `.venv`, `.env`, API keys hoặc `.streamlit/secrets.toml`.
App chạy không cần Gemini key; nhập key vào thanh bên trái nếu muốn tải danh sách
model hoặc bật tóm tắt AI. Chọn nhiều model và bật **Tự chuyển model khi lỗi** để
thử model kế tiếp khi model trước tạm thời không khả dụng.

### Gemini API key

Nhập Gemini API key trực tiếp vào ô **Gemini API key** trong thanh bên trái.
Key được giữ trong phiên dashboard và che trong giao diện. Danh sách model được
tải theo key đang nhập. Nếu key bị Gemini từ chối, hết hiệu lực hoặc thiếu quyền,
dashboard thông báo và yêu cầu nhập key khác. Không lưu key vào Google Sheets,
repo hoặc file cấu hình.

Tin tức vẫn được lấy từ Google News RSS; Gemini key được dùng cho danh sách model
và tính năng tóm tắt AI. Khi Google News không mở được bài, bộ đọc đối chiếu tiêu
đề trên trang báo và tìm đường dẫn qua RSS, trang danh mục hoặc sitemap công khai.
`news_source_links.json` bổ sung các liên kết đã xác minh nhưng bị thiếu trong danh
mục của báo, có kiểm tra ngày và tiêu đề trước khi dùng. Công bố doanh nghiệp có
thể đọc từ bản đăng lại trên CafeF; giao diện ghi rõ nguồn nội dung thực tế. PDF
có chữ được trích xuất bằng pypdf; PDF ảnh quét và ảnh tài liệu trong bài 24HMoney
được gửi cùng yêu cầu Gemini khi bật AI. Nút tải lại xử lý cả lỗi lấy nội dung và
lỗi tóm tắt AI.
Theme nằm ở `.streamlit/config.toml`, style ở `assets/editorial.css`.
League Spartan có font dự phòng; giao diện hỗ trợ bàn phím và reduced motion.
