import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'models/clothes.dart';

class ReportScreen extends StatelessWidget {
  const ReportScreen({super.key, this.onDeleted});

  final VoidCallback? onDeleted;

  @override
  Widget build(BuildContext context) {
    final routeArgs = ModalRoute.of(context)?.settings.arguments;
    final Clothes? passedItem = routeArgs is Clothes ? routeArgs : null;

    final closetProvider = context.watch<ClosetProvider>();
    final item = passedItem ?? closetProvider.currentReportItem;

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final backgroundColor = isDark
        ? const Color(0xFF121212)
        : const Color(0xFFF8F9FC);
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor = isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade200;
    final primaryText = isDark ? Colors.white : const Color(0xFF1A1A1A);
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF5F6368);
    if (item == null) {
      return Center(
        child: Text(
          '아직 등록된 의류가 없습니다.\n스캔 탭에서 케어 라벨을 촬영해 보세요.',
          textAlign: TextAlign.center,
          style: TextStyle(color: secondaryText, fontSize: 16),
        ),
      );
    }

    final materialsText = item.materials.entries
        .map((e) => '${e.key.toUpperCase()} ${_formatMaterialValue(e.value)}%')
        .join(', ');

    final careTips = _buildCareTips(item);
    final storageTip = _buildStorageTip(item);
    final disposalGuide = _buildDisposalGuide(item);
    final mainMaterial = _mainMaterialLabel(item);

    return Container(
      color: backgroundColor,
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(24, 24, 24, 140),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.verified_user_outlined,
                  color: Color(0xFF4A4EFE),
                  size: 28,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '디지털 제품 여권 (DPP)',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: primaryText,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              item.title,
              style: TextStyle(
                color: primaryText,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              '소재 정보와 생산·제조 탄소 추정값을 확인하세요.',
              style: TextStyle(color: secondaryText, fontSize: 14),
            ),
            const SizedBox(height: 16),

            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _buildTagChip(
                  icon: Icons.category_outlined,
                  label: item.category,
                  isDark: isDark,
                ),
                _buildTagChip(
                  icon: Icons.layers_outlined,
                  label: mainMaterial,
                  isDark: isDark,
                ),
              ],
            ),
            const SizedBox(height: 24),

            LayoutBuilder(
              builder: (context, constraints) {
                final textScale = MediaQuery.textScalerOf(context).scale(1);
                final useVerticalLayout =
                    constraints.maxWidth < 300 || textScale > 1.35;
                final carbonCard = _buildSummaryCard(
                  title: '탄소 추정값',
                  value: '${item.carbonFootprint.toStringAsFixed(1)} kg',
                  subtitle:
                      item.carbonFootprintSource == CarbonFootprintSource.server
                      ? item.carbonFootprintMin != null &&
                                item.carbonFootprintMax != null
                            ? '${item.carbonFootprintMin!.toStringAsFixed(1)}~${item.carbonFootprintMax!.toStringAsFixed(1)} kg CO2eq'
                            : 'CO2eq 기준 서버 계산값'
                      : 'CO2eq 기준 임시 추정값',
                  icon: Icons.eco_outlined,
                  color: const Color(0xFF4A4EFE),
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                  cardColor: cardColor,
                  borderColor: borderColor,
                );
                final materialCard = _buildSummaryCard(
                  title: '주요 소재',
                  value: mainMaterial,
                  subtitle: materialsText.isEmpty ? '소재 정보 없음' : materialsText,
                  icon: Icons.checkroom_outlined,
                  color: Colors.green,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                  cardColor: cardColor,
                  borderColor: borderColor,
                );

                if (useVerticalLayout) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      carbonCard,
                      const SizedBox(height: 12),
                      materialCard,
                    ],
                  );
                }

                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: carbonCard),
                    const SizedBox(width: 12),
                    Expanded(child: materialCard),
                  ],
                );
              },
            ),
            const SizedBox(height: 24),

            Text(
              '생산·제조 탄소 배출량',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: primaryText,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '이 수치는 전체 생애주기 배출량이 아닙니다. 소재와 무게를 바탕으로 생산·제조 과정에서 발생한 탄소 배출량을 추정한 값입니다.',
              style: TextStyle(color: secondaryText, fontSize: 13),
            ),
            const SizedBox(height: 16),

            _buildProductionCarbonCard(
              item,
              primaryText: primaryText,
              secondaryText: secondaryText,
              cardColor: cardColor,
              borderColor: borderColor,
              isDark: isDark,
            ),
            const SizedBox(height: 12),

            _buildCarbonComparisonCard(
              item,
              primaryText: primaryText,
              secondaryText: secondaryText,
              cardColor: cardColor,
              borderColor: borderColor,
              isDark: isDark,
            ),
            const SizedBox(height: 12),

            _buildCarbonScopeNotice(
              primaryText: primaryText,
              secondaryText: secondaryText,
              isDark: isDark,
            ),
            const SizedBox(height: 24),

            Text(
              '맞춤 관리 가이드',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: primaryText,
              ),
            ),
            const SizedBox(height: 12),

            _buildGuideSection(
              title: '세탁 및 관리 팁',
              icon: Icons.local_laundry_service_outlined,
              color: Colors.blue,
              children: careTips,
              primaryText: primaryText,
              secondaryText: secondaryText,
              cardColor: cardColor,
              borderColor: borderColor,
            ),
            const SizedBox(height: 12),

            _buildGuideSection(
              title: '보관 팁',
              icon: Icons.inventory_2_outlined,
              color: Colors.deepPurple,
              children: [storageTip],
              primaryText: primaryText,
              secondaryText: secondaryText,
              cardColor: cardColor,
              borderColor: borderColor,
            ),
            const SizedBox(height: 24),

            Text(
              '관리 정보',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: primaryText,
              ),
            ),
            const SizedBox(height: 12),

            _buildHistoryRow(
              '주요 소재',
              materialsText.isEmpty ? '정보 없음' : materialsText,
              primaryText: primaryText,
              secondaryText: secondaryText,
            ),
            _buildHistoryRow(
              '세탁 지침',
              item.careInstruction.isEmpty ? '정보 없음' : item.careInstruction,
              primaryText: primaryText,
              secondaryText: secondaryText,
            ),
            _buildHistoryRow(
              '권장 조치',
              item.health <= 20 ? '재사용·기부·분리배출 검토' : '현재 관리 방식 유지',
              primaryText: primaryText,
              secondaryText: secondaryText,
            ),
            const SizedBox(height: 32),

            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () =>
                    _showDisposalBottomSheet(context, item, disposalGuide),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.green,
                  minimumSize: const Size.fromHeight(54),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 14,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.recycling, color: Colors.white),
                    SizedBox(width: 8),
                    Flexible(
                      child: Text(
                        '올바른 폐기 방법 보기',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),

            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: () =>
                    _confirmDelete(context, item, onDeleted: onDeleted),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(52),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 14,
                  ),
                  side: const BorderSide(color: Colors.redAccent, width: 1.5),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.delete_outline, color: Colors.redAccent),
                    SizedBox(width: 8),
                    Flexible(
                      child: Text(
                        '이 의류 삭제하기',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: Colors.redAccent,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static Future<void> _confirmDelete(
    BuildContext context,
    Clothes item, {
    VoidCallback? onDeleted,
  }) async {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          backgroundColor: isDark ? const Color(0xFF1C1C1E) : Colors.white,
          title: Text(
            '의류 삭제',
            style: TextStyle(
              color: isDark ? Colors.white : const Color(0xFF111111),
            ),
          ),
          content: Text(
            '"${item.title}"을(를) 삭제할까요?\n이 작업은 되돌릴 수 없습니다.',
            style: TextStyle(
              height: 1.5,
              color: isDark ? const Color(0xFFD1D1D6) : const Color(0xFF444444),
            ),
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
              child: const Text('삭제', style: TextStyle(color: Colors.white)),
            ),
          ],
        );
      },
    );

    if (confirmed != true) return;

    if (!context.mounted) return;

    await context.read<ClosetProvider>().removeClothes(item);

    if (!context.mounted) return;

    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text('"${item.title}"이(가) 삭제되었습니다.')));

    if (onDeleted != null) {
      onDeleted();
      return;
    }

    Navigator.pushReplacementNamed(context, '/main', arguments: 2);
  }

  static String _formatMaterialValue(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }
    return value.toStringAsFixed(1);
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

    tips.add('착용 후 바로 보관하기보다 잠시 통풍시키고, 세탁 전에는 케어 라벨의 온도와 건조 지침을 먼저 확인하세요.');

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
    if (_hasMaterial(item, ['cotton', 'linen', 'wool'])) {
      return '천연섬유 비중이 높다면 오염과 손상 정도를 직접 확인한 뒤 의류수거함, 기부, 업사이클링 활용 가능성을 검토해 보세요.';
    }

    if (_hasMaterial(item, ['polyester', 'nylon', 'polyurethane'])) {
      return '혼방·합성섬유 의류는 지역 분리배출 기준을 먼저 확인하고, 재사용이 어렵다고 판단될 때 의류 수거 체계에 맞춰 배출하세요.';
    }

    return '의류의 오염과 손상 정도를 직접 확인한 뒤 재사용, 기부, 지역 의류 수거 기준을 순서대로 검토해 보세요.';
  }

  static void _showDisposalBottomSheet(
    BuildContext context,
    Clothes item,
    String disposalGuide,
  ) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final backgroundColor = isDark ? const Color(0xFF121212) : Colors.white;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText = isDark ? const Color(0xFFD1D1D6) : Colors.black87;

    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      backgroundColor: backgroundColor,
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
                Text(
                  '권장 폐기 및 재사용 가이드',
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                    color: primaryText,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  disposalGuide,
                  style: TextStyle(
                    fontSize: 14,
                    height: 1.6,
                    color: secondaryText,
                  ),
                ),
                const SizedBox(height: 16),
                _buildBottomSheetBullet(
                  '상태가 양호하면 중고 거래 또는 기부를 먼저 검토하세요.',
                  secondaryText,
                ),
                _buildBottomSheetBullet(
                  '혼방 소재는 지역 의류 수거 기준을 확인한 뒤 배출하세요.',
                  secondaryText,
                ),
                _buildBottomSheetBullet(
                  '오염이 심한 경우 재사용 가능 여부를 먼저 판단한 뒤 처리하세요.',
                  secondaryText,
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

  static Widget _buildBottomSheetBullet(String text, Color textColor) {
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
              style: TextStyle(fontSize: 14, height: 1.5, color: textColor),
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
    required Color primaryText,
    required Color secondaryText,
    required Color cardColor,
    required Color borderColor,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color),
          const SizedBox(height: 12),
          Text(title, style: TextStyle(color: secondaryText, fontSize: 12)),
          const SizedBox(height: 6),
          Text(
            value,
            style: TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.bold,
              color: primaryText,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            subtitle,
            style: TextStyle(fontSize: 12, color: secondaryText, height: 1.4),
          ),
        ],
      ),
    );
  }

  Widget _buildProductionCarbonCard(
    Clothes item, {
    required Color primaryText,
    required Color secondaryText,
    required Color cardColor,
    required Color borderColor,
    required bool isDark,
  }) {
    final sourceText =
        item.carbonFootprintSource == CarbonFootprintSource.server
        ? item.carbonFootprintMin != null && item.carbonFootprintMax != null
              ? '서버 계산값 · ${item.carbonFootprintMin!.toStringAsFixed(1)}~${item.carbonFootprintMax!.toStringAsFixed(1)} kg CO2eq 범위'
              : '서버 계산값'
        : '앱 임시 추정값';

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: const Color(
                    0xFF4A4EFE,
                  ).withValues(alpha: isDark ? 0.22 : 0.10),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Icon(
                  Icons.factory_outlined,
                  color: Color(0xFF4A4EFE),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '생산·제조 과정 추정값',
                      style: TextStyle(
                        color: secondaryText,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      '${item.carbonFootprint.toStringAsFixed(1)} kg CO2eq',
                      style: TextStyle(
                        color: primaryText,
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      sourceText,
                      style: TextStyle(
                        color: secondaryText,
                        fontSize: 12,
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          _buildScopeRow(
            icon: Icons.check_circle_outline,
            label: '포함',
            value: '소재, 혼용률, 의류 무게 기준',
            color: Colors.green,
            primaryText: primaryText,
            secondaryText: secondaryText,
          ),
          const SizedBox(height: 8),
          _buildScopeRow(
            icon: Icons.info_outline,
            label: '미포함',
            value: '운송, 사용, 세탁, 폐기 과정',
            color: Colors.orange,
            primaryText: primaryText,
            secondaryText: secondaryText,
          ),
        ],
      ),
    );
  }

  Widget _buildCarbonComparisonCard(
    Clothes item, {
    required Color primaryText,
    required Color secondaryText,
    required Color cardColor,
    required Color borderColor,
    required bool isDark,
  }) {
    final carbon = item.carbonFootprint <= 0 ? 0.1 : item.carbonFootprint;
    final comparisons = [
      _CarbonComparisonData(
        icon: Icons.directions_car_filled_outlined,
        title: '자동차',
        value: '약 ${_formatImpactValue(carbon / 0.2)} km',
      ),
      _CarbonComparisonData(
        icon: Icons.smartphone_outlined,
        title: '스마트폰',
        value: '약 ${_formatImpactValue(carbon / 0.012)}회 충전',
      ),
      _CarbonComparisonData(
        icon: Icons.lightbulb_outline,
        title: 'LED 전구',
        value: '약 ${_formatImpactValue(carbon / 0.02)}시간',
      ),
    ];

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '탄소 배출량 체감',
            style: TextStyle(
              color: primaryText,
              fontSize: 16,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '이 옷의 추정 배출량은 생활 속 기준으로 보면 아래와 비슷해요.',
            style: TextStyle(color: secondaryText, fontSize: 13, height: 1.5),
          ),
          const SizedBox(height: 14),
          LayoutBuilder(
            builder: (context, constraints) {
              final textScale = MediaQuery.textScalerOf(context).scale(1);
              final useVerticalLayout =
                  constraints.maxWidth < 330 || textScale > 1.35;

              if (useVerticalLayout) {
                return Column(
                  children: [
                    for (final comparison in comparisons) ...[
                      _buildComparisonTile(
                        comparison,
                        primaryText: primaryText,
                        secondaryText: secondaryText,
                        isDark: isDark,
                      ),
                      if (comparison != comparisons.last)
                        const SizedBox(height: 10),
                    ],
                  ],
                );
              }

              return Row(
                children: [
                  for (final comparison in comparisons) ...[
                    Expanded(
                      child: _buildComparisonTile(
                        comparison,
                        primaryText: primaryText,
                        secondaryText: secondaryText,
                        isDark: isDark,
                      ),
                    ),
                    if (comparison != comparisons.last)
                      const SizedBox(width: 10),
                  ],
                ],
              );
            },
          ),
          const SizedBox(height: 12),
          Text(
            '비교값은 수치를 쉽게 이해하기 위한 대략적인 환산입니다.',
            style: TextStyle(color: secondaryText, fontSize: 12, height: 1.4),
          ),
        ],
      ),
    );
  }

  Widget _buildCarbonScopeNotice({
    required Color primaryText,
    required Color secondaryText,
    required bool isDark,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E2A3A) : const Color(0xFFEEF4FF),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isDark ? const Color(0xFF30445F) : const Color(0xFFD9E6FF),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline, color: Color(0xFF4A4EFE), size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              '운송, 사용, 세탁, 폐기 과정의 배출량은 현재 수치에 포함하지 않습니다.',
              style: TextStyle(color: secondaryText, fontSize: 13, height: 1.5),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildScopeRow({
    required IconData icon,
    required String label,
    required String value,
    required Color color,
    required Color primaryText,
    required Color secondaryText,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: color, size: 18),
        const SizedBox(width: 8),
        SizedBox(
          width: 52,
          child: Text(
            label,
            style: TextStyle(
              color: primaryText,
              fontSize: 13,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(color: secondaryText, fontSize: 13, height: 1.4),
          ),
        ),
      ],
    );
  }

  Widget _buildComparisonTile(
    _CarbonComparisonData data, {
    required Color primaryText,
    required Color secondaryText,
    required bool isDark,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF2A2A2E) : const Color(0xFFF6F7FB),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Icon(data.icon, color: const Color(0xFF4A4EFE), size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  data.title,
                  style: TextStyle(color: secondaryText, fontSize: 12),
                ),
                const SizedBox(height: 4),
                Text(
                  data.value,
                  style: TextStyle(
                    color: primaryText,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String _formatImpactValue(double value) {
    if (!value.isFinite || value <= 0) return '1';

    if (value < 10) {
      final rounded = value.toStringAsFixed(1);
      return rounded.endsWith('.0')
          ? rounded.substring(0, rounded.length - 2)
          : rounded;
    }

    if (value < 100) {
      return value.round().toString();
    }

    return ((value / 10).round() * 10).toString();
  }

  Widget _buildGuideSection({
    required String title,
    required IconData icon,
    required Color color,
    required List<String> children,
    required Color primaryText,
    required Color secondaryText,
    required Color cardColor,
    required Color borderColor,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: color),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                    color: primaryText,
                  ),
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
                      style: TextStyle(
                        fontSize: 14,
                        height: 1.5,
                        color: secondaryText,
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

  Widget _buildHistoryRow(
    String title,
    String value, {
    required Color primaryText,
    required Color secondaryText,
  }) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final textScale = MediaQuery.textScalerOf(context).scale(1);
        final useVerticalLayout =
            constraints.maxWidth < 320 || textScale > 1.35;
        final titleWidget = Text(
          title,
          style: TextStyle(color: secondaryText, fontSize: 15),
        );
        final valueWidget = Text(
          value,
          style: TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 15,
            height: 1.5,
            color: primaryText,
          ),
          textAlign: useVerticalLayout ? TextAlign.left : TextAlign.right,
        );

        return Padding(
          padding: const EdgeInsets.only(bottom: 10.0),
          child: useVerticalLayout
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    titleWidget,
                    const SizedBox(height: 4),
                    valueWidget,
                  ],
                )
              : Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(width: 100, child: titleWidget),
                    Expanded(child: valueWidget),
                  ],
                ),
        );
      },
    );
  }

  static Widget _buildTagChip({
    required IconData icon,
    required String label,
    required bool isDark,
  }) {
    final bgColor = isDark ? const Color(0xFF232A45) : const Color(0xFFEEF1FF);

    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 220),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: bgColor,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: const Color(0xFF4A4EFE)),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                label,
                softWrap: true,
                style: const TextStyle(
                  color: Color(0xFF4A4EFE),
                  fontWeight: FontWeight.w600,
                  fontSize: 12,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CarbonComparisonData {
  const _CarbonComparisonData({
    required this.icon,
    required this.title,
    required this.value,
  });

  final IconData icon;
  final String title;
  final String value;
}
