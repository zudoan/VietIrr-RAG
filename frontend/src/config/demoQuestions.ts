/**
 * BỘ CÂU HỎI THỬ NGHIỆM THỰC TẾ TRÊN GIAO DIỆN WEB (VERIFIED DEMO QUESTIONS)
 * Toàn bộ các câu hỏi đã được kiểm định nguồn gốc tài liệu PDF thật và chạy thực nghiệm qua:
 * R6 Hybrid Retrieval -> Qwen2.5:7B -> Citation Guard -> Provenance Tracing.
 * 
 * Kiểm toán và đối chiếu PDF: 30/10/2026
 */

export type DemoVerificationStatus = 'E2E_VERIFIED' | 'EXPECTED_ABSTENTION' | 'SOURCE_VERIFIED'

export interface DemoQuestionItem {
  id: string
  group: 'Số liệu đơn lẻ' | 'So sánh & Bảng' | 'Khí tượng & Hồ chứa' | 'Giới hạn hệ thống'
  category: string
  title: string
  query: string
  expectedAnswer: string
  documentId?: string
  documentTitle?: string
  pageNumber?: number
  type: 'FACTUAL_SUCCESS' | 'SAFETY_ABSTAIN'
  verificationStatus: DemoVerificationStatus
  badge: string
}

export const VERIFIED_DEMO_QUESTIONS: DemoQuestionItem[] = [
  {
    id: 'DEMO_01',
    group: 'Số liệu đơn lẻ',
    category: 'Cống Hàm Giang',
    title: 'Cao trình đáy cống Hàm Giang',
    query: 'Theo báo cáo Nam Măng Thít năm 2024, cao trình đáy của cống Hàm Giang là bao nhiêu mét?',
    expectedAnswer: 'Cao trình đáy của cống Hàm Giang là -3 m (Bảng STT 8, trang 56).',
    documentId: 'IRR_CTL_2024_9a520097',
    documentTitle: 'Báo cáo giám sát, dự báo chất lượng nước hệ thống Nam Măng Thít năm 2024',
    pageNumber: 56,
    type: 'FACTUAL_SUCCESS',
    verificationStatus: 'E2E_VERIFIED',
    badge: 'Xác minh PDF (Trang 56)',
  },
  {
    id: 'DEMO_02',
    group: 'Số liệu đơn lẻ',
    category: 'Cống Long Hiệp',
    title: 'Cao trình đáy cống Long Hiệp',
    query: 'Theo báo cáo Nam Măng Thít năm 2024, cao trình đáy của cống Long Hiệp là bao nhiêu mét?',
    expectedAnswer: 'Cao trình đáy của cống Long Hiệp (cống Bình Tân) là -2 m (Bảng STT 14, trang 56).',
    documentId: 'IRR_CTL_2024_9a520097',
    documentTitle: 'Báo cáo giám sát, dự báo chất lượng nước hệ thống Nam Măng Thít năm 2024',
    pageNumber: 56,
    type: 'FACTUAL_SUCCESS',
    verificationStatus: 'E2E_VERIFIED',
    badge: 'Xác minh PDF (Trang 56)',
  },
  {
    id: 'DEMO_03',
    group: 'So sánh & Bảng',
    category: 'Bắc Trang & Bông Bót',
    title: 'So sánh cống Bắc Trang và cống Bông Bót',
    query: 'Theo báo cáo Nam Măng Thít năm 2024, cao trình đáy của cống Bắc Trang và cống Bông Bót lần lượt là bao nhiêu?',
    expectedAnswer: 'Cao trình đáy của cống Bắc Trang là -3 m và cống Bông Bót là -4,5 m (Bảng trang 56).',
    documentId: 'IRR_CTL_2024_9a520097',
    documentTitle: 'Báo cáo giám sát, dự báo chất lượng nước hệ thống Nam Măng Thít năm 2024',
    pageNumber: 56,
    type: 'FACTUAL_SUCCESS',
    verificationStatus: 'E2E_VERIFIED',
    badge: '2/2 Citations (Trang 56)',
  },
  {
    id: 'DEMO_04',
    group: 'So sánh & Bảng',
    category: 'Hàm Giang & Long Hiệp',
    title: 'So sánh cống Hàm Giang và cống Long Hiệp',
    query: 'Theo báo cáo Nam Măng Thít năm 2024, cao trình đáy của cống Hàm Giang và cống Long Hiệp lần lượt là bao nhiêu?',
    expectedAnswer: 'Cao trình đáy của cống Hàm Giang là -3 m và cống Long Hiệp là -2 m (Bảng trang 56).',
    documentId: 'IRR_CTL_2024_9a520097',
    documentTitle: 'Báo cáo giám sát, dự báo chất lượng nước hệ thống Nam Măng Thít năm 2024',
    pageNumber: 56,
    type: 'FACTUAL_SUCCESS',
    verificationStatus: 'E2E_VERIFIED',
    badge: '2/2 Citations (Trang 56)',
  },
  {
    id: 'DEMO_05',
    group: 'Khí tượng & Hồ chứa',
    category: 'Lưu vực sông Hoàng Long',
    title: 'Lượng mưa trạm Ninh Bình',
    query: 'Theo Bản tin dự báo nguồn nước Lưu vực sông Hoàng Long (Từ 01/6 đến 30/6/2019), lượng mưa trong tháng 5, từ 1/5 đến 28/5/2019 của NINH BÌNH được ghi nhận là bao nhiêu?',
    expectedAnswer: 'Lượng mưa tại Ninh Bình trong tháng 5 từ 1/5 đến 28/5/2019 là 239 mm (đạt 139% TBNN).',
    documentId: 'IRR_CTL_2019_1fc21515',
    documentTitle: 'Bản tin dự báo nguồn nước Lưu vực sông Hoàng Long (Từ 01/6 đến 30/6/2019)',
    pageNumber: 1,
    type: 'FACTUAL_SUCCESS',
    verificationStatus: 'E2E_VERIFIED',
    badge: 'Xác minh PDF (Trang 1)',
  },
  {
    id: 'DEMO_06',
    group: 'Khí tượng & Hồ chứa',
    category: 'Lưu vực sông Thương',
    title: 'Dự báo lượng mưa trạm Hữu Lũng',
    query: 'Theo Bản tin dự báo nguồn nước Lưu vực sông Thương (kỳ từ 19/7 đến 25/7/2019), dự báo lượng mưa tuần tới tại trạm Hữu Lũng là bao nhiêu mm?',
    expectedAnswer: 'Dự báo lượng mưa tuần tới tại trạm Hữu Lũng là 119 mm (Bảng 1, trang 1).',
    documentId: 'IRR_CTL_2019_a1445f42',
    documentTitle: 'Bản tin dự báo nguồn nước Lưu vực sông Thương (Từ 19/7 đến 25/7/2019)',
    pageNumber: 1,
    type: 'FACTUAL_SUCCESS',
    verificationStatus: 'E2E_VERIFIED',
    badge: 'Xác minh PDF (Trang 1)',
  },
  {
    id: 'DEMO_07',
    group: 'Khí tượng & Hồ chứa',
    category: 'Lưu vực sông Lục Nam',
    title: 'Diện tích đáp ứng hồ Suối Mỡ',
    query: 'Theo Bản tin dự báo nguồn nước Lưu vực sông Lục Nam từ 19/7 đến 25/7/2019, diện tích đáp ứng của hồ Suối Mỡ là bao nhiêu ha?',
    expectedAnswer: 'Diện tích đáp ứng của hồ Suối Mỡ là 67 ha (Bảng 3 chỉ tiêu hồ chứa).',
    documentId: 'IRR_CTL_2019_645d37d3',
    documentTitle: 'Bản tin dự báo nguồn nước Lưu vực sông Lục Nam (Từ 19/7 đến 25/7/2019)',
    pageNumber: 4,
    type: 'FACTUAL_SUCCESS',
    verificationStatus: 'E2E_VERIFIED',
    badge: 'Xác minh PDF (Trang 4)',
  },
  {
    id: 'DEMO_08',
    group: 'Giới hạn hệ thống',
    category: 'Ngoài phạm vi tài liệu',
    title: 'Hồ Bản Chát (Ngoài phạm vi tài liệu)',
    query: 'Cao trình mực nước chết và dung tích hữu ích của hồ Bản Chát là bao nhiêu theo tài liệu lưu vực sông Hoàng Long?',
    expectedAnswer: 'Hệ thống từ chối an toàn có căn cứ: hồ Bản Chát thuộc hệ thống Lai Châu/sông Đà, không có trong dữ liệu sông Hoàng Long, không hallucinate số liệu.',
    type: 'SAFETY_ABSTAIN',
    verificationStatus: 'EXPECTED_ABSTENTION',
    badge: 'Từ chối an toàn (Fail-closed)',
  },
  {
    id: 'DEMO_09',
    group: 'Giới hạn hệ thống',
    category: 'Câu hỏi dở dang',
    title: 'Truy vấn phân mảnh chưa rõ vị ngữ',
    query: 'Theo dự báo nguồn nước phục vụ sản xuất nông nghiệp thuộc tỉnh Ninh Bình năm 2019',
    expectedAnswer: 'Hệ thống nhận diện câu hỏi thiếu vị ngữ/thông số cần tra cứu và hướng dẫn người dùng bổ sung thông tin thay vì phỏng đoán sai lệch.',
    type: 'SAFETY_ABSTAIN',
    verificationStatus: 'EXPECTED_ABSTENTION',
    badge: 'Yêu cầu làm rõ (Ambiguous)',
  },
]
