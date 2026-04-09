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

    final lcaStages = _buildLcaBreakdown(item);
    final careTips = _buildCareTips(item);
    final storageTip = _buildStorageTip(item);
    final disposalGuide = _buildDisposalGuide(item);
    final healthLabel = _healthLabel(item.health);
    final mainMaterial = _mainMaterialLabel(item);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(
                Icons.verified_user_outlined,
                color: Color(0xFF4A4EFE),
                size: 28,
              ),
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
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _buildTagChip(icon: Icons.category_outlined, label: item.category),
              _buildTagChip(icon: Icons.layers_outlined, label: mainMaterial),
              _buildTagChip(icon: Icons.favorite_border, label: healthLabel),
            ],
          ),
          const SizedBox(height: 24),

          _buildHealthStatusCard(item.health),
          const SizedBox(height: 24),

          Row(
            children: [
              Expanded(
                child: _buildSummaryCard(
                  title: '총 탄소발자국',
                  value: '${item.carbonFootprint.toStringAsFixed(1)} kg',
                  subtitle: 'CO2eq 기준 추정',
                  icon: Icons.eco_outlined,
                  color: const Color(0xFF4A4EFE),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildSummaryCard(
                  title: '주요 소재',
                  value: mainMaterial,
                  subtitle: materialsText.isEmpty ? '정보 없음' : materialsText,
                  icon: Icons.checkroom_outlined,
                  color: Colors.green,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),

          const Text(
            '단계별 탄소 배출량 (LCA)',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text(
            '총 ${item.carbonFootprint.toStringAsFixed(1)} kg CO2eq · 소재/카테고리 기반 추정',
            style: const TextStyle(color: Colors.grey, fontSize: 13),
          ),
          const SizedBox(height: 16),

          _buildLcaChart(item, lcaStages),
          const SizedBox(height: 12),

          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.orange.shade50,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.orange.shade100),
            ),
            child: const Text(
              '원단 생산 단계의 배출량이 가장 큰 경우가 많습니다. 소재 선택과 세탁 습관을 함께 관리하면 의류의 전 생애주기 환경 부담을 줄이는 데 도움이 됩니다.',
              style: TextStyle(
                fontSize: 13,
                color: Colors.black87,
                height: 1.5,
              ),
            ),
          ),
          const SizedBox(height: 24),

          const Text(
            '맞춤 관리 가이드',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),

          _buildGuideSection(
            title: '세탁 및 관리 팁',
            icon: Icons.local_laundry_service_outlined,
            color: Colors.blue,
            children: careTips,
          ),
          const SizedBox(height: 12),

          _buildGuideSection(
            title: '보관 팁',
            icon: Icons.inventory_2_outlined,
            color: Colors.deepPurple,
            children: [storageTip],
          ),
          const SizedBox(height: 24),

          const Text(
            '관리 이력',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),

          _buildHistoryRow(
            '주요 소재',
            materialsText.isEmpty ? '정보 없음' : materialsText,
          ),
          _buildHistoryRow(
            '세탁 지침',
            item.careInstruction.isEmpty ? '정보 없음' : item.careInstruction,
          ),
          _buildHistoryRow(
            '권장 조치',
            item.health <= 20 ? '재사용·기부·분리배출 검토' : '현재 관리 방식 유지',
          ),
          const SizedBox(height: 32),

          SizedBox(
            width: double.infinity,
            height: 54,
            child: OutlinedButton.icon(
              onPressed: () => _showCertificateDialog(context, item),
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
              onPressed: () => _showDisposalBottomSheet(
                context,
                item,
                disposalGuide,
              ),
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
          const SizedBox(height: 12),

          SizedBox(
            width: double.infinity,
            height: 52,
            child: OutlinedButton.icon(
              onPressed: () => _confirmDelete(context, item),
              icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
              label: const Text(
                '이 의류 삭제하기',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: Colors.redAccent,
                ),
              ),
              style: OutlinedButton.styleFrom(
                side: const BorderSide(color: Colors.redAccent, width: 1.5),
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

  static Future<void> _confirmDelete(BuildContext context, Clothes item) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('의류 삭제'),
          content: Text(
            '"${item.title}"을(를) 옷장에서 삭제할까요?\n삭제 후에는 홈/옷장/리포트에 반영됩니다.',
            style: const TextStyle(height: 1.5),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('취소'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.redAccent,
              ),
              child: const Text(
                '삭제',
                style: TextStyle(color: Colors.white),
              ),
            ),
          ],
        );
      },
    );

    if (confirmed != true) return;

    await context.read<ClosetProvider>().removeClothes(item);

    if (!context.mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('"${item.title}"이(가) 삭제되었습니다.')),
    );

    Navigator.pushReplacementNamed(
      context,
      '/main',
      arguments: 3,
    );
  }

  static String _formatMaterialValue(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }
    return value.toStringAsFixed(1);
  }

  static String _healthLabel(int health) {
    if (health <= 20) return '수명 만료 주의';
    if (health <= 40) return '관리 주의';
    if (health <= 70) return '보통';
    return '양호';
  }

  static String _mainMaterialLabel(Clothes item) {
    if (item.materials.isEmpty) return '소재 정보 없음';

    final sorted = item.materials.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return '${sorted.first.key.toUpperCase()} ${_formatMaterialValue(sorted.first.value)}%';
  }

  static bool _hasMaterial(Clothes item, List<String> keywords) {
    final lowerKeys = item.materials.keys.map((e) => e.toLowerCase()).toList();
    return lowerKeys.any(
          (key) => keywords.any((keyword) => key.contains(keyword)),
    );
  }

  static List<String> _buildCareTips(Clothes item) {
    final tips = <String>[];

    if (_hasMaterial(item, ['cotton', 'linen'])) {
      tips.add('면/린넨 계열은 미지근한 물 세탁과 자연 건조가 수명 유지에 도움이 됩니다.');
    }

    if (_hasMaterial(item, ['polyester', 'nylon'])) {
      tips.add('합성섬유는 높은 온도에 약할 수 있어 건조기 사용을 줄이는 것이 좋습니다.');
    }

    if (_hasMaterial(item, ['wool', 'silk'])) {
      tips.add('울/실크 계열은 마찰과 열에 민감하므로 중성세제와 약한 세탁 코스를 권장합니다.');
    }

    if (_hasMaterial(item, ['polyurethane', 'spandex'])) {
      tips.add('신축성 섬유가 포함된 의류는 비틀어 짜기보다 눌러서 물기를 제거하는 편이 안전합니다.');
    }

    if (item.health <= 20) {
      tips.add('현재 건강도가 낮아 추가 세탁 전 오염 부위만 부분 세탁하는 방식이 더 적합할 수 있습니다.');
    } else if (item.health <= 40) {
      tips.add('세탁 빈도를 줄이고 통풍 보관을 병행하면 의류 수명 저하를 완화할 수 있습니다.');
    } else {
      tips.add('현재 상태가 양호하므로 라벨 지침을 유지하면 비교적 안정적으로 관리할 수 있습니다.');
    }

    if (item.careInstruction.isNotEmpty) {
      tips.add('라벨 지침: ${item.careInstruction}');
    }

    return tips;
  }

  static String _buildStorageTip(Clothes item) {
    if (_hasMaterial(item, ['wool', 'knit'])) {
      return '니트/울 계열은 걸어두기보다 접어서 보관하면 늘어남을 줄일 수 있습니다.';
    }

    if (_hasMaterial(item, ['silk'])) {
      return '실크 계열은 직사광선을 피해 통풍이 되는 곳에 보관하는 것이 좋습니다.';
    }

    if (_hasMaterial(item, ['linen', 'cotton'])) {
      return '면/린넨 계열은 충분히 건조한 뒤 보관하면 냄새와 곰팡이 위험을 줄일 수 있습니다.';
    }

    return '착용 후 바로 보관하기보다 잠시 통풍시킨 뒤 정리하면 의류 컨디션 유지에 도움이 됩니다.';
  }

  static String _buildDisposalGuide(Clothes item) {
    if (item.health > 40) {
      return '아직 사용 가능한 상태입니다. 중고 거래, 기부, 재사용을 우선 검토해 보세요.';
    }

    if (_hasMaterial(item, ['cotton', 'linen', 'wool'])) {
      return '천연섬유 비중이 높다면 상태에 따라 의류수거함, 기부, 업사이클링 활용 가능성을 먼저 확인해 보세요.';
    }

    if (_hasMaterial(item, ['polyester', 'nylon', 'polyurethane'])) {
      return '혼방·합성섬유 의류는 지역 분리배출 기준을 우선 확인하고, 재사용이 어렵다면 의류 수거 체계에 맞춰 배출하세요.';
    }

    return '상태가 좋지 않다면 지역 의류 수거 또는 섬유 분리배출 기준을 확인해 적절히 처리하는 것이 좋습니다.';
  }

  static List<_LcaStageData> _buildLcaBreakdown(Clothes item) {
    final totalFootprint = item.carbonFootprint > 0 ? item.carbonFootprint : 10.0;

    final syntheticShare = _sumMatchingMaterials(
      item.materials,
      ['polyester', 'nylon', 'polyurethane', 'spandex', 'acrylic'],
    );

    final animalFiberShare = _sumMatchingMaterials(
      item.materials,
      ['wool', 'silk', 'leather'],
    );

    final plantFiberShare = _sumMatchingMaterials(
      item.materials,
      ['cotton', 'organic cotton', 'linen', 'hemp'],
    );

    final blendComplexity = item.materials.length >= 3
        ? 0.02
        : item.materials.length == 2
        ? 0.01
        : 0.0;

    double rawMaterialRatio =
        0.48 +
            (syntheticShare / 100 * 0.10) +
            (animalFiberShare / 100 * 0.08) -
            (plantFiberShare / 100 * 0.05);

    double manufacturingRatio =
        0.22 + (item.category == '하의' ? 0.02 : 0.0) + blendComplexity;

    double transportRatio = 0.12 + (item.category == '하의' ? 0.01 : 0.0);

    rawMaterialRatio = rawMaterialRatio.clamp(0.40, 0.62);
    manufacturingRatio = manufacturingRatio.clamp(0.18, 0.28);
    transportRatio = transportRatio.clamp(0.10, 0.16);

    double careRatio =
        1 - rawMaterialRatio - manufacturingRatio - transportRatio;

    if (careRatio < 0.12) {
      final shortage = 0.12 - careRatio;
      rawMaterialRatio -= shortage * 0.6;
      manufacturingRatio -= shortage * 0.3;
      transportRatio -= shortage * 0.1;
      careRatio = 0.12;
    }

    final ratioSum =
        rawMaterialRatio + manufacturingRatio + transportRatio + careRatio;

    final normalizedRaw = rawMaterialRatio / ratioSum;
    final normalizedManufacturing = manufacturingRatio / ratioSum;
    final normalizedTransport = transportRatio / ratioSum;
    final normalizedCare = careRatio / ratioSum;

    return [
      _LcaStageData(
        label: '원단 생산',
        ratio: normalizedRaw,
        carbonKg: totalFootprint * normalizedRaw,
        color: Colors.redAccent,
      ),
      _LcaStageData(
        label: '제조 공정',
        ratio: normalizedManufacturing,
        carbonKg: totalFootprint * normalizedManufacturing,
        color: Colors.orangeAccent,
      ),
      _LcaStageData(
        label: '운송 및 유통',
        ratio: normalizedTransport,
        carbonKg: totalFootprint * normalizedTransport,
        color: const Color(0xFF7C83FD),
      ),
      _LcaStageData(
        label: '세탁 및 관리',
        ratio: normalizedCare,
        carbonKg: totalFootprint * normalizedCare,
        color: Colors.green,
      ),
    ];
  }

  static double _sumMatchingMaterials(
      Map<String, double> materials,
      List<String> keywords,
      ) {
    double total = 0.0;

    for (final entry in materials.entries) {
      final lowerKey = entry.key.toLowerCase();
      final isMatch = keywords.any((keyword) => lowerKey.contains(keyword));
      if (isMatch) {
        total += entry.value;
      }
    }

    return total;
  }

  static void _showCertificateDialog(BuildContext context, Clothes item) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('DPP 인증서 발급'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.verified,
                color: Color(0xFF4A4EFE),
                size: 52,
              ),
              const SizedBox(height: 16),
              Text(
                '${item.title}의 DPP 요약 인증서를 발급할 수 있습니다.',
                textAlign: TextAlign.center,
                style: const TextStyle(height: 1.5),
              ),
              const SizedBox(height: 12),
              Text(
                '현재는 시연용 안내 단계이며, 이후 QR 기반 인증서 공유 기능과 연결할 예정입니다.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.grey.shade700,
                  fontSize: 13,
                  height: 1.5,
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('닫기'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('확인'),
            ),
          ],
        );
      },
    );
  }

  static void _showDisposalBottomSheet(
      BuildContext context,
      Clothes item,
      String disposalGuide,
      ) {
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '권장 폐기 및 재사용 가이드',
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  disposalGuide,
                  style: const TextStyle(
                    fontSize: 14,
                    height: 1.6,
                    color: Colors.black87,
                  ),
                ),
                const SizedBox(height: 16),
                _buildBottomSheetBullet(
                  '상태가 양호하면 중고 거래 또는 기부를 먼저 검토하세요.',
                ),
                _buildBottomSheetBullet(
                  '혼방 소재는 지역 의류 수거 기준을 확인한 뒤 배출하세요.',
                ),
                _buildBottomSheetBullet(
                  '오염이 심한 경우 재사용 가능 여부를 먼저 판단한 뒤 처리하세요.',
                ),
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton(
                    onPressed: () => Navigator.pop(context),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.green,
                    ),
                    child: const Text(
                      '확인했어요',
                      style: TextStyle(color: Colors.white),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  static Widget _buildBottomSheetBullet(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 5),
            child: Icon(Icons.circle, size: 8, color: Colors.green),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(fontSize: 14, height: 1.5),
            ),
          ),
        ],
      ),
    );
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
                .withValues(alpha: 0.30),
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
              color: Colors.white.withValues(alpha: 0.20),
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

  Widget _buildSummaryCard({
    required String title,
    required String value,
    required String subtitle,
    required IconData icon,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color),
          const SizedBox(height: 12),
          Text(
            title,
            style: const TextStyle(
              color: Colors.grey,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            value,
            style: const TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            subtitle,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 12,
              color: Colors.grey,
              height: 1.4,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLcaChart(Clothes item, List<_LcaStageData> stages) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        children: [
          ...stages.map((stage) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: _buildChartBar(stage),
            );
          }),
          const SizedBox(height: 4),
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              '${item.category} · 총 ${item.carbonFootprint.toStringAsFixed(1)} kg CO2eq',
              style: const TextStyle(
                color: Colors.grey,
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildChartBar(_LcaStageData stage) {
    final percent = (stage.ratio * 100).round();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                stage.label,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            Text(
              '${stage.carbonKg.toStringAsFixed(1)} kg',
              style: const TextStyle(
                fontSize: 12,
                color: Colors.black87,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(width: 8),
            Text(
              '$percent%',
              style: const TextStyle(
                fontSize: 12,
                color: Colors.grey,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Stack(
          children: [
            Container(
              height: 16,
              decoration: BoxDecoration(
                color: Colors.grey.shade100,
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            FractionallySizedBox(
              widthFactor: stage.ratio,
              child: Container(
                height: 16,
                decoration: BoxDecoration(
                  color: stage.color,
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildGuideSection({
    required String title,
    required IconData icon,
    required Color color,
    required List<String> children,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: color),
              const SizedBox(width: 8),
              Text(
                title,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          ...children.map(
                (tip) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(top: 6),
                    child: Icon(
                      Icons.circle,
                      size: 8,
                      color: Color(0xFF4A4EFE),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      tip,
                      style: const TextStyle(
                        fontSize: 14,
                        height: 1.5,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHistoryRow(String title, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10.0),
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
              style: const TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 15,
                height: 1.5,
              ),
              textAlign: TextAlign.right,
            ),
          ),
        ],
      ),
    );
  }

  static Widget _buildTagChip({
    required IconData icon,
    required String label,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFFEEF1FF),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: const Color(0xFF4A4EFE)),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(
              color: Color(0xFF4A4EFE),
              fontWeight: FontWeight.w600,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}

class _LcaStageData {
  final String label;
  final double ratio;
  final double carbonKg;
  final Color color;

  const _LcaStageData({
    required this.label,
    required this.ratio,
    required this.carbonKg,
    required this.color,
  });
}