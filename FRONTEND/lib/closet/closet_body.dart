part of '../closet_screen.dart';

/// 옷장 상단 상태와 탭별 목록을 조합해 화면 본문을 만듭니다.
extension _ClosetBody on _ClosetScreenState {
  Widget _buildClosetBody(BuildContext context) {
    // Provider 원본에서 검색·정렬된 탭별 표시 목록을 매 빌드마다 계산합니다.
    final clothesList = context.watch<ClosetProvider>().items;
    final originalOrder = clothesList.toList();
    final palette = _ClosetPalette.from(context);

    // 전체를 한 번만 정렬한 뒤 분류로 나눠 빌드당 정렬 비용을 1회로 줄입니다.
    final sortedItems = _sortClothes(
      List<Clothes>.from(clothesList),
      originalOrder,
    );
    final allItems = _filterClothes(sortedItems);
    final topItems = _filterClothes(
      sortedItems.where((item) => item.category == '상의').toList(),
    );
    final bottomItems = _filterClothes(
      sortedItems.where((item) => item.category == '하의').toList(),
    );

    return DefaultTabController(
      length: 3,
      child: Column(
        children: [
          _selectionMode
              ? _buildSelectionHeader(palette)
              : _buildBrowseHeader(palette),
          _buildCategoryTabBar(palette),
          Expanded(
            child: TabBarView(
              children: [
                _buildCategoryTab(
                  context: context,
                  items: allItems,
                  originalOrder: originalOrder,
                  emptyMessage: '옷장에 등록된 의류가 없습니다.',
                  palette: palette,
                ),
                _buildCategoryTab(
                  context: context,
                  items: topItems,
                  originalOrder: originalOrder,
                  emptyMessage: '상의 의류가 없습니다.',
                  palette: palette,
                ),
                _buildCategoryTab(
                  context: context,
                  items: bottomItems,
                  originalOrder: originalOrder,
                  emptyMessage: '하의 의류가 없습니다.',
                  palette: palette,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// 다중 선택 중에는 선택 개수와 취소·삭제 동작만 표시합니다.
  Widget _buildSelectionHeader(_ClosetPalette palette) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${_selectedItems.length}개 선택됨',
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.bold,
              color: palette.primaryText,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              TextButton(
                onPressed: _exitSelectionMode,
                child: const Text('선택 취소'),
              ),
              const SizedBox(width: 8),
              ElevatedButton.icon(
                onPressed: _deleteSelectedItems,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.redAccent,
                ),
                icon: const Icon(Icons.delete_outline, color: Colors.white),
                label: const Text(
                  '선택 삭제',
                  style: TextStyle(color: Colors.white),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// 일반 상태에서는 정렬·순서 편집·검색 도구를 표시합니다.
  Widget _buildBrowseHeader(_ClosetPalette palette) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
      child: Column(
        children: [
          Stack(
            alignment: Alignment.center,
            children: [
              Align(
                alignment: Alignment.center,
                child: Text(
                  '내 옷장',
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: palette.primaryText,
                  ),
                ),
              ),
              Align(
                alignment: Alignment.centerRight,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (_sortOption == ClosetSortOption.custom)
                      TextButton(
                        onPressed: _toggleReorderMode,
                        child: Text(_reorderMode ? '완료' : '편집'),
                      ),
                    IconButton(
                      onPressed: _showSortBottomSheet,
                      tooltip: '옷장 정렬',
                      icon: const Icon(
                        Icons.sort,
                        color: AppPalette.accent,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            '현재 정렬: $_sortLabel',
            style: TextStyle(color: palette.secondaryText, fontSize: 13),
          ),
          const SizedBox(height: 6),
          Text(
            _sortOption == ClosetSortOption.custom
                ? (_reorderMode
                      ? '드래그해서 순서를 바꿔 보세요.'
                      : '내 설정 순으로 정렬되어 있어요.')
                : '원하는 방식으로 옷장을 정리해 보세요.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: palette.secondaryText,
              fontSize: 12,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 14),
          _buildSearchField(palette),
        ],
      ),
    );
  }

  /// 검색어 입력과 초기화 버튼을 제공하는 검색창입니다.
  Widget _buildSearchField(_ClosetPalette palette) {
    return TextField(
      controller: _searchController,
      style: TextStyle(color: palette.primaryText, fontSize: 14),
      textInputAction: TextInputAction.search,
      decoration: InputDecoration(
        hintText: '옷 이름, 소재 검색',
        hintStyle: TextStyle(color: palette.secondaryText, fontSize: 14),
        prefixIcon: Icon(
          Icons.search,
          color: palette.secondaryText,
          size: 21,
        ),
        suffixIcon: _searchQuery.isEmpty
            ? null
            : IconButton(
                onPressed: _searchController.clear,
                tooltip: '검색어 지우기',
                icon: Icon(
                  Icons.close,
                  color: palette.secondaryText,
                  size: 20,
                ),
              ),
        filled: true,
        fillColor: palette.cardColor,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 14,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: palette.borderColor),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: palette.borderColor),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: AppPalette.accent, width: 1.4),
        ),
      ),
    );
  }

  /// 전체·상의·하의 목록 사이를 전환하는 탭입니다.
  Widget _buildCategoryTabBar(_ClosetPalette palette) {
    return TabBar(
      labelColor: AppPalette.accent,
      unselectedLabelColor: palette.secondaryText,
      indicatorColor: AppPalette.accent,
      indicatorWeight: 3,
      tabs: const [
        Tab(text: '전체'),
        Tab(text: '상의'),
        Tab(text: '하의'),
      ],
    );
  }

  /// 현재 모드에 따라 일반 목록과 순서 변경 목록 중 하나를 선택합니다.
  Widget _buildCategoryTab({
    required BuildContext context,
    required List<Clothes> items,
    required List<Clothes> originalOrder,
    required String emptyMessage,
    required _ClosetPalette palette,
  }) {
    final resolvedEmptyMessage = _emptyMessage(emptyMessage);

    if (_sortOption == ClosetSortOption.custom && _reorderMode) {
      return _buildReorderableClothesList(
        context,
        items,
        originalOrder,
        emptyMessage: resolvedEmptyMessage,
        palette: palette,
      );
    }

    return _buildClothesList(
      context,
      items,
      emptyMessage: resolvedEmptyMessage,
      palette: palette,
    );
  }
}

/// 밝은 테마와 어두운 테마에서 목록이 함께 사용하는 색상 묶음입니다.
class _ClosetPalette {
  const _ClosetPalette({
    required this.primaryText,
    required this.secondaryText,
    required this.cardColor,
    required this.borderColor,
    required this.selectedBgColor,
    required this.warningBgColor,
    required this.leadingBgColor,
    required this.shadowColor,
    required this.isDark,
  });

  factory _ClosetPalette.from(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return _ClosetPalette(
      primaryText: isDark ? Colors.white : const Color(0xFF1A1A1A),
      secondaryText: isDark
          ? const Color(0xFFD1D1D6)
          : const Color(0xFF5F6368),
      cardColor: isDark ? const Color(0xFF1C1C1E) : Colors.white,
      borderColor: isDark
          ? const Color(0xFF2C2C2E)
          : Colors.grey.shade200,
      selectedBgColor: isDark
          ? const Color(0xFF232A45)
          : const Color(0xFFEEF1FF),
      warningBgColor: isDark
          ? const Color(0xFF2A1E1E)
          : Colors.red.shade50,
      leadingBgColor: isDark
          ? const Color(0xFF2A2A2E)
          : Colors.grey.shade100,
      shadowColor: isDark
          ? Colors.black.withValues(alpha: 0.16)
          : Colors.black.withValues(alpha: 0.03),
      isDark: isDark,
    );
  }

  final Color primaryText;
  final Color secondaryText;
  final Color cardColor;
  final Color borderColor;
  final Color selectedBgColor;
  final Color warningBgColor;
  final Color leadingBgColor;
  final Color shadowColor;
  final bool isDark;
}
