import 'package:flutter/material.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 1. 환영 인사
          const Text(
            '안녕하세요, 홍길동님! 🌱',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Color(0xFF1A1A1A)),
          ),
          const SizedBox(height: 8),
          const Text(
            '오늘도 지속 가능한 의류 관리를 실천해 보세요.',
            style: TextStyle(fontSize: 14, color: Colors.grey),
          ),
          const SizedBox(height: 32),

          // 2. 총 탄소 발자국 대시보드
          _buildCarbonDashboard(),
          const SizedBox(height: 24),

          // 3. 오늘의 날씨 맞춤 팁
          _buildWeatherTip(),
          const SizedBox(height: 24),

          // 4. 최근 등록한 옷 기대 수명
          const Text(
            '최근 등록한 의류 상태',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),
          _buildLifeExpectancyCard('오가닉 코튼 맨투맨', 85, '앞으로 약 25회 더 세탁 가능'),
          const SizedBox(height: 12),
          _buildLifeExpectancyCard('리사이클 폴리 아노락', 60, '건조기 사용을 피해 수명을 늘려주세요'),
        ],
      ),
    );
  }

  // 탄소 발자국 카드 위젯
  Widget _buildCarbonDashboard() {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF4A4EFE),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(color: const Color(0xFF4A4EFE).withOpacity(0.3), blurRadius: 15, offset: const Offset(0, 8)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '내 옷장 탄소 절감 효과',
            style: TextStyle(color: Colors.white70, fontSize: 14),
          ),
          const SizedBox(height: 8),
          const Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '12.5',
                style: TextStyle(color: Colors.white, fontSize: 36, fontWeight: FontWeight.bold),
              ),
              SizedBox(width: 4),
              Text(
                'kg CO2eq',
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.2),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.park, color: Colors.white, size: 18),
                SizedBox(width: 8),
                Text('소나무 약 2그루를 심은 효과예요!', style: TextStyle(color: Colors.white, fontSize: 13)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // 날씨 맞춤 팁 카드 위젯
  Widget _buildWeatherTip() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.shade200),
        boxShadow: [
          BoxShadow(color: Colors.black.withOpacity(0.02), blurRadius: 10, offset: const Offset(0, 4)),
        ],
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: Colors.blue.shade50, shape: BoxShape.circle),
            child: const Icon(Icons.water_drop_outlined, color: Colors.blue),
          ),
          const SizedBox(width: 16),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('오늘의 관리 팁', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                SizedBox(height: 4),
                Text('비가 와서 습도가 높아요. 린넨이나 실크 소재는 통풍이 잘 되는 곳에 보관해 주세요.',
                    style: TextStyle(color: Colors.grey, fontSize: 13, height: 1.4)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // 기대 수명 게이지 카드 위젯
  Widget _buildLifeExpectancyCard(String title, int percentage, String subtitle) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
              Text('$percentage%', style: TextStyle(fontWeight: FontWeight.bold, color: percentage > 70 ? Colors.green : Colors.orange)),
            ],
          ),
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: percentage / 100,
              backgroundColor: Colors.grey.shade200,
              color: percentage > 70 ? Colors.green : Colors.orange,
              minHeight: 8,
            ),
          ),
          const SizedBox(height: 12),
          Text(subtitle, style: const TextStyle(color: Colors.grey, fontSize: 12)),
        ],
      ),
    );
  }
}