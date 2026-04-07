import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'models/clothes.dart';

class ReportScreen extends StatelessWidget {
  const ReportScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final routeArgs = ModalRoute.of(context)?.settings.arguments;
    final Clothes? passedItem = routeArgs is Clothes ? routeArgs : null;

    final closetProvider = context.watch<ClosetProvider>();
    final item = passedItem ?? closetProvider.currentReportItem;

    if (item == null) {
      return const Center(
        child: Text(
          '아직 옷장에 등록된 옷이 없습니다.\n스캔 탭에서 옷을 등록해 주세요!',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey, fontSize: 16),
        ),
      );
    }

    final materialsText = item.materials.entries
        .map((e) => '${e.key.toUpperCase()} ${_formatMaterialValue(e.value)}%')
        .join(', ');

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.verified_user_outlined,
                  color: Color(0xFF4A4EFE), size: 28),
              SizedBox(width: 8),
              Text(
                '디지털 제품 여권 (DPP)',
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF1A1A1A),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '홍길동님의 ${item.title}',
            style: const TextStyle(color: Colors.grey, fontSize: 14),
          ),
          const SizedBox(height: 32),
          _buildHealthStatusCard(item.health),
          const SizedBox(height: 24),
          const Text(
            '단계별 탄소 배출량 (LCA)',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),
          _buildLcaChartMockup(),
          const SizedBox(height: 24),
          const Text(
            '관리 이력',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),
          _buildHistoryRow('주요 소재', materialsText.isEmpty ? '정보 없음' : materialsText),
          _buildHistoryRow(
            '세탁 지침',
            item.careInstruction.isEmpty ? '정보 없음' : item.careInstruction,
          ),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            height: 54,
            child: OutlinedButton.icon(
              onPressed: () {},
              icon: const Icon(Icons.qr_code, color: Color(0xFF4A4EFE)),
              label: const Text(
                '중고 거래용 DPP 인증서 발급',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF4A4EFE),
                ),
              ),
              style: OutlinedButton.styleFrom(
                side: const BorderSide(color: Color(0xFF4A4EFE), width: 2),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            height: 54,
            child: ElevatedButton.icon(
              onPressed: () {},
              icon: const Icon(Icons.recycling, color: Colors.white),
              label: const Text(
                '올바른 폐기 방법 보기',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.green,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  static String _formatMaterialValue(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }
    return value.toStringAsFixed(1);
  }

  Widget _buildHealthStatusCard(int health) {
    final isWarning = health <= 20;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: isWarning
              ? [Colors.redAccent, Colors.orangeAccent]
              : [const Color(0xFF4A4EFE), const Color(0xFF6B72FF)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: (isWarning ? Colors.redAccent : const Color(0xFF4A4EFE))
                .withOpacity(0.3),
            blurRadius: 10,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '현재 건강 상태',
                style: TextStyle(color: Colors.white70, fontSize: 14),
              ),
              const SizedBox(height: 4),
              Text(
                '$health%',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.2),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              children: [
                Icon(
                  isWarning
                      ? Icons.warning_amber_rounded
                      : Icons.timer_outlined,
                  color: Colors.white,
                  size: 18,
                ),
                const SizedBox(width: 6),
                Text(
                  isWarning ? '수명 만료' : '세탁 양호',
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLcaChartMockup() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        children: [
          _buildChartBar('원단 생산', 60, Colors.redAccent),
          const SizedBox(height: 12),
          _buildChartBar('운송 및 제조', 20, Colors.orangeAccent),
          const SizedBox(height: 12),
          _buildChartBar('세탁 및 관리', 15, const Color(0xFF4A4EFE)),
        ],
      ),
    );
  }

  Widget _buildChartBar(String label, int flexValue, Color color) {
    return Row(
      children: [
        SizedBox(
          width: 100,
          child: Text(
            label,
            style: const TextStyle(fontSize: 13, color: Colors.black87),
          ),
        ),
        Expanded(
          flex: 100,
          child: Stack(
            children: [
              Container(
                height: 16,
                decoration: BoxDecoration(
                  color: Colors.grey.shade100,
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
              FractionallySizedBox(
                widthFactor: flexValue / 100,
                child: Container(
                  height: 16,
                  decoration: BoxDecoration(
                    color: color,
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
              ),
            ],
          ),
        ),
        SizedBox(
          width: 40,
          child: Text(
            ' $flexValue%',
            textAlign: TextAlign.right,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
          ),
        ),
      ],
    );
  }

  Widget _buildHistoryRow(String title, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 100,
            child: Text(
              title,
              style: const TextStyle(color: Colors.grey, fontSize: 15),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
              textAlign: TextAlign.right,
            ),
          ),
        ],
      ),
    );
  }
}