// 소재·탄소 요약, 계산 근거와 생활 속 비교 UI를 구성합니다.
part of '../report_screen.dart';

String _formatMaterialValue(double value) {
  if (value % 1 == 0) {
    return value.toInt().toString();
  }
  return value.toStringAsFixed(1);
}

// 합산·표시 이름 변환을 마친 소재 중 혼용률이 가장 높은 것을 대표 소재로 표시합니다.
// 합산 전에 고르면 '면 30 + cotton 30'이 폴리에스터 40에 밀립니다. 비율이 같으면 먼저 나온 소재입니다.
String _mainMaterialLabel(List<MapEntry<String, double>> materialEntries) {
  if (materialEntries.isEmpty) return '소재 정보 없음';

  final main = materialEntries.reduce(
    (current, next) => next.value > current.value ? next : current,
  );

  return '${main.key} ${_formatMaterialValue(main.value)}%';
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

// 계산 출처와 포함·미포함 범위를 함께 보여 주는 핵심 탄소 카드입니다.
Widget _buildProductionCarbonCard(
  Clothes item, {
  required Color primaryText,
  required Color secondaryText,
  required Color accentColor,
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
                color: AppPalette.accent.withValues(alpha: isDark ? 0.22 : 0.10),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Icon(
                Icons.factory_outlined,
                color: accentColor,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '원료·소재 생산 단계 추정값',
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
          value: '봉제·제조, 운송, 사용, 세탁, 폐기 과정',
          color: Colors.orange,
          primaryText: primaryText,
          secondaryText: secondaryText,
        ),
        // 출처는 접지 않습니다. IDEMAT 계수를 쓰는 조건이 출처 표기('data from www.ecocostsvalue.com')라
        // 늘 보여야 합니다(BACKEND/policies/idemat_2026_free_public_selection.json required_attribution).
        const SizedBox(height: 12),
        Text(
          '출처: ${_carbonSourceLabel(item)}',
          style: TextStyle(color: secondaryText, fontSize: 12, height: 1.5),
        ),
        const SizedBox(height: 4),
        _buildCalculationBasisFold(
          item,
          primaryText: primaryText,
          secondaryText: secondaryText,
          accentColor: accentColor,
        ),
      ],
    ),
  );
}

// 계산 범위·무게·가정·한계를 한곳에 모아 '계산 기준 보기'로 접어 둡니다. 예전엔 탄소 카드 안과
// 아래 '계산 기준' 카드·미포함 안내 상자에 나뉘어 출처·범위가 두세 번 되풀이됐습니다(DECISIONS 2026-11-07).
// 서버의 계산식(calculation_basis)은 무게 줄과 겹쳐 보이지 않습니다. 서버의 calculation_note 는
// V2 일 때만 보입니다 — 옛 서버 값의 메모는 팀 내부 메모('최종 발표 전 팀 승인 출처로 교체…')라
// 옷과 함께 폰에 남아 있어 여기서 거릅니다(DECISIONS 227).
Widget _buildCalculationBasisFold(
  Clothes item, {
  required Color primaryText,
  required Color secondaryText,
  required Color accentColor,
}) {
  final scope = item.carbonFootprintSource == CarbonFootprintSource.server
      ? item.calculationScope
      : null;
  final lines = [
    scope != null
        ? _calculationScopeLabel(scope)
        : '범위: 원료 및 소재 생산 단계 추정',
    '무게: ${_weightBasisText(item)}',
    _carbonAssumptionText(item),
    if (scope == 'fiber_production_estimate' && item.calculationNote != null)
      item.calculationNote!,
  ];

  // 펼치고 접을 때 위아래 테두리가 생기지 않게 두 모양을 빈 테두리로 둡니다.
  return ExpansionTile(
    tilePadding: EdgeInsets.zero,
    childrenPadding: const EdgeInsets.only(bottom: 4),
    expandedCrossAxisAlignment: CrossAxisAlignment.start,
    shape: const Border(),
    collapsedShape: const Border(),
    iconColor: accentColor,
    collapsedIconColor: secondaryText,
    title: Text(
      '계산 기준 보기',
      style: TextStyle(
        color: primaryText,
        fontSize: 13,
        fontWeight: FontWeight.w700,
      ),
    ),
    children: [
      for (final line in lines)
        Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Text(
            line,
            style: TextStyle(color: secondaryText, fontSize: 12, height: 1.5),
          ),
        ),
    ],
  );
}

// 서버가 내려준 계산 범위 코드를 사용자 문구로 바꿉니다.
String _calculationScopeLabel(String scope) {
  if (scope == 'fiber_production_estimate') {
    // V2 계수는 원료부터 섬유까지만 담는다(BACKEND/policies/idemat_2026_free_public_selection.json
    // 의 excluded). '섬유 생산 단계'는 원단(textile)까지로도 읽혀 이름 대신 빠진 공정을 적는다.
    return '범위: 원료에서 섬유까지(실·원단 만들기, 염색, 봉제는 빠짐)';
  }
  if (scope == 'material_production_estimate') {
    return '범위: 원료 및 소재 생산 단계 추정';
  }
  return '범위: $scope';
}

// 서버가 내려준 출처 이름을 사용자 문구로 바꿉니다. 서버의 지금 이름은 영어 개발용 이름표라
// 한국어로 보이되, 계수가 아직 추정값인 것은 그대로 알립니다(DECISIONS 227).
String _calculationSourceLabel(String source) {
  if (source == 'K-DPP 소재별 배출계수 표(추정값)' ||
      source == 'K-DPP backend material carbon factor table (development estimates)') {
    return '기존 추정 계수(문헌 출처 미확정)';
  }
  return source;
}

// 미국 EPA 환산 기준을 참고한 생활 속 탄소 비교 계수입니다. (develop d0df5a4 기준)
const double _smartphoneChargeKgCo2Eq = 0.0124;
const double _led10WKgCo2EqPerHour = 0.004;

// kg CO2eq를 자동차 거리·충전 횟수·전구 사용 시간으로 단순 환산합니다.
Widget _buildCarbonComparisonCard(
  Clothes item, {
  required Color primaryText,
  required Color secondaryText,
  required Color accentColor,
  required Color cardColor,
  required Color borderColor,
  required bool isDark,
}) {
  final carbon = item.carbonFootprint <= 0 ? 0.1 : item.carbonFootprint;
  final comparisons = [
    _CarbonComparisonData(
      icon: Icons.directions_car_filled_outlined,
      title: '자동차',
      value: '약 ${formatImpactValue(carbon / passengerCarKgCo2EqPerKm)} km',
    ),
    _CarbonComparisonData(
      icon: Icons.smartphone_outlined,
      title: '스마트폰',
      value: '약 ${formatImpactValue(carbon / _smartphoneChargeKgCo2Eq)}회 충전',
    ),
    _CarbonComparisonData(
      icon: Icons.lightbulb_outline,
      title: 'LED 전구',
      value: '약 ${formatImpactValue(carbon / _led10WKgCo2EqPerHour)}시간',
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
                      accentColor: accentColor,
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
                      accentColor: accentColor,
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
          '비교값은 사용자 이해를 위한 참고 환산값이며 공식 인증값이 아닙니다. '
          '미국 EPA 환산 기준을 참고해 자동차 0.244 kg CO2eq/km, '
          '스마트폰 완전 충전 0.0124 kg CO2eq/회를 적용했습니다. '
          'LED 전구는 10W 소비전력 기준 0.004 kg CO2eq/시간으로 계산했습니다.',
          style: TextStyle(color: secondaryText, fontSize: 12, height: 1.4),
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
  required Color accentColor,
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
        Icon(data.icon, color: accentColor, size: 22),
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

String _carbonSourceLabel(Clothes item) {
  if (item.carbonFootprintSource == CarbonFootprintSource.localEstimate) {
    return '앱 임시 계수(기존 추정값·문헌 출처 미확정)';
  }
  final source = item.calculationSource?.trim();
  return source == null || source.isEmpty
      ? '기존 서버 계산 · 계수 출처 미확인'
      : _calculationSourceLabel(source);
}

// 최소·최대 무게가 같으면 추정 범위가 아니라 사용자가 입력한 실제 무게입니다.
bool _hasExactWeight(Clothes item) {
  final minWeight = item.minWeightGram;
  final maxWeight = item.maxWeightGram;

  return minWeight != null &&
      maxWeight != null &&
      (maxWeight - minWeight).abs() <= 0.05;
}

// 계산에 깔린 가정과 결과의 한계를 알립니다(협의안 R3).
// 저장된 옷에는 어느 부위의 조성인지 남지 않아 겉감이라고 단정하지 않습니다.
String _carbonAssumptionText(Clothes item) {
  final weightBasis = _hasExactWeight(item) ? '입력한 무게' : '추정 무게';

  // 서버 V2 안내문(calculation_note)이 같은 가정을 이미 말하면 '계산 기준 보기' 안에서 두 번 읽히므로 뺍니다.
  final noteSaysFiberMass =
      item.calculationNote?.contains('총무게를 섬유 무게로') ?? false;
  final versionNote = item.calculationScope == 'fiber_production_estimate'
      ? '${noteSaysFiberMass ? '' : ' 총무게를 섬유 무게로 가정합니다.'} 기존·임시 추정값과 기준이 달라 서로의 차이를 감축량으로 비교할 수 없어요.'
      : ' 기존 추정값이며 지금 계수로 다시 계산한 결과가 아닙니다.';
  return '저장된 소재 조성과 $weightBasis 기준이며, 옷의 부위별 구성이나 생산 국가·공정 등에 따라 달라질 수 있어요.$versionNote';
}

// 실제 무게가 하나의 값인지 범위인지에 따라 계산 근거 문구를 구성합니다.
String _weightBasisText(Clothes item) {
  final minWeight = item.minWeightGram;
  final maxWeight = item.maxWeightGram;

  if (minWeight == null || maxWeight == null) {
    return '저장된 소재와 의류 유형 기준';
  }

  if (_hasExactWeight(item)) {
    return '실제 무게 ${_formatWeightGram(maxWeight)}g';
  }

  return '${item.weightSource == 'catalog' ? '유형별 임시 대표 무게·범위' : '선택 무게 범위'} ${_formatWeightGram(minWeight)}~${_formatWeightGram(maxWeight)}g';
}

String _formatWeightGram(double value) {
  if (value % 1 == 0) {
    return value.toInt().toString();
  }

  return value.toStringAsFixed(1);
}

// 생활 속 탄소 비교 항목의 아이콘·이름·환산값을 묶는 표시용 데이터입니다.
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
