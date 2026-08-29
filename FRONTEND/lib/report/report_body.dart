// 리포트 데이터와 화면 전체 섹션의 배치를 연결합니다.
part of '../report_screen.dart';

// 서버 저장 ID를 우선 사용해 전달된 의류와 현재 Provider 항목을 연결합니다.
Clothes? _resolveDisplayItem(
  ClosetProvider provider,
  Clothes? passedItem,
) {
  if (passedItem == null) {
    return provider.currentReportItem;
  }

  final savedResultId = passedItem.savedResultId;

  if (savedResultId != null) {
    for (final item in provider.items) {
      if (item.savedResultId == savedResultId) {
        return item;
      }
    }
  }

  for (final item in provider.items) {
    if (identical(item, passedItem)) {
      return item;
    }
  }

  return passedItem;
}

Widget _buildReportBody(
  BuildContext context, {
  VoidCallback? onDeleted,
}) {
  // 경로 인수로 받은 항목도 Provider의 최신 저장본으로 다시 연결해 수정 결과를 즉시 반영합니다.
  final routeArgs = ModalRoute.of(context)?.settings.arguments;
  final Clothes? passedItem = routeArgs is Clothes ? routeArgs : null;

  final closetProvider = context.watch<ClosetProvider>();
  final item =
      _resolveDisplayItem(closetProvider, passedItem) ??
      closetProvider.currentReportItem;

  final isDark = Theme.of(context).brightness == Brightness.dark;
  final palette = AppPalette.of(context);
  final backgroundColor = palette.background;
  final cardColor = palette.card;
  final borderColor = isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade200;
  final primaryText = isDark ? Colors.white : const Color(0xFF1A1A1A);
  final secondaryText = palette.textSecondary;
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
                color: AppPalette.accent,
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
              IconButton(
                onPressed: () => _showEditBottomSheet(context, item),
                tooltip: '의류 정보 수정',
                icon: Icon(Icons.edit_outlined, color: secondaryText),
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

          // 좁은 화면이나 큰 글자에서는 요약 카드를 세로로 배치합니다.
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
                color: AppPalette.accent,
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
          const SizedBox(height: 12),

          _buildCalculationBasisCard(
            item,
            primaryText: primaryText,
            secondaryText: secondaryText,
            cardColor: cardColor,
            borderColor: borderColor,
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
