part of '../closet_screen.dart';

/// 정렬 기준 선택 시트와 각 옵션의 시각 표현을 담당합니다.
extension _ClosetSortSheet on _ClosetScreenState {
  /// 정렬 기준 선택 시트를 열고 선택 결과를 화면 상태에 반영합니다.
  Future<void> _showSortBottomSheet() async {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final primaryText = palette.textPrimary;
    final sheetColor = isDark ? const Color(0xFF121212) : Colors.white;

    final selected = await showModalBottomSheet<ClosetSortOption>(
      context: context,
      showDragHandle: true,
      backgroundColor: sheetColor,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) {
        return SafeArea(
          // 작은 화면이나 큰 글자 설정에서 옵션이 잘리지 않도록 스크롤을 허용합니다.
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '정렬',
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: primaryText,
                  ),
                ),
                const SizedBox(height: 20),
                _buildSortOptionTile(
                  label: '친환경 순',
                  value: ClosetSortOption.eco,
                  primaryText: primaryText,
                ),
                _buildSortOptionTile(
                  label: '건강도 순',
                  value: ClosetSortOption.health,
                  primaryText: primaryText,
                ),
                _buildSortOptionTile(
                  label: '최신 등록 순',
                  value: ClosetSortOption.latest,
                  primaryText: primaryText,
                ),
                _buildSortOptionTile(
                  label: '내 설정 순',
                  value: ClosetSortOption.custom,
                  primaryText: primaryText,
                ),
              ],
            ),
          ),
        );
      },
    );

    // 시트가 닫히는 사이 화면이 사라졌을 수 있으므로 상태 갱신 전에 확인합니다.
    if (selected == null || !mounted) return;

    final provider = context.read<ClosetProvider>();

    if (selected != ClosetSortOption.custom) {
      _updateState(() => _reorderMode = false);
    }

    // Provider가 값을 먼저 반영하고 알리므로 화면은 곧바로 새 기준으로 그려집니다.
    // 저장에 실패하면 Provider가 되돌리고, 화면도 같은 값을 보므로 함께 되돌아갑니다.
    try {
      await provider.setClosetSortOption(selected);
    } catch (_) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('정렬 방식을 저장하지 못해 이전 기준으로 되돌렸어요.')),
      );
    }
  }

  /// 정렬 시트의 한 옵션과 현재 선택 상태를 표시합니다.
  Widget _buildSortOptionTile({
    required String label,
    required ClosetSortOption value,
    required Color primaryText,
  }) {
    final isSelected = _sortOption == value;

    // 넷 중 하나를 고르는 자리이므로 선택한 항목에만 체크를 두고 나머지는 비웁니다.
    // 체크와 빈 원을 섞으면 짝이 맞지 않고, 전부 라디오 원으로 맞추면 목록이
    // 입력 폼처럼 번잡해 보여 팀 검토에서 체크 방식으로 정했습니다(2026-09-10).
    // 선택 상태를 색·아이콘으로만 알리면 낭독기에서는 네 항목이 구분되지 않으므로
    // Semantics로 함께 전달하고, 내부 표현은 중복 낭독을 막습니다.
    return Semantics(
      label: '$label 정렬',
      button: true,
      selected: isSelected,
      child: InkWell(
        onTap: () => Navigator.pop(context, value),
        borderRadius: BorderRadius.circular(14),
        child: ExcludeSemantics(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    label,
                    style: TextStyle(
                      fontSize: 18,
                      color: isSelected ? AppPalette.accent : primaryText,
                      fontWeight:
                          isSelected ? FontWeight.bold : FontWeight.normal,
                    ),
                  ),
                ),
                // 선택되지 않은 줄에도 아이콘 크기만큼 자리를 두어 네 줄의 높이를 같게 맞춥니다.
                if (isSelected)
                  const Icon(Icons.check, color: AppPalette.accent)
                else
                  const SizedBox(width: 24, height: 24),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
