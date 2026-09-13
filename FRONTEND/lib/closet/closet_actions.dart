part of '../closet_screen.dart';

/// 검색·정렬·선택·삭제·순서 변경처럼 상태를 바꾸는 동작을 모읍니다.
extension _ClosetActions on _ClosetScreenState {
  /// 검색창 내용을 비교용 소문자 검색어로 동기화합니다.
  void _handleSearchChanged() {
    final nextQuery = _searchController.text.trim().toLowerCase();

    if (nextQuery == _searchQuery) return;

    _updateState(() {
      _searchQuery = nextQuery;
    });
  }

  /// 현재 정렬 기준을 화면에 표시할 이름으로 바꿉니다.
  String get _sortLabel {
    switch (_sortOption) {
      case ClosetSortOption.eco:
        return '친환경 순';
      case ClosetSortOption.health:
        return '건강도 순';
      case ClosetSortOption.latest:
        return '최신 등록 순';
      case ClosetSortOption.custom:
        return '내 설정 순';
    }
  }

  /// Provider 원본은 건드리지 않고 현재 기준으로 복사본만 정렬합니다.
  List<Clothes> _sortClothes(
    List<Clothes> source,
    List<Clothes> originalOrder,
  ) {
    final sorted = List<Clothes>.from(source);

    switch (_sortOption) {
      case ClosetSortOption.eco:
        sorted.sort((a, b) => a.carbonFootprint.compareTo(b.carbonFootprint));
        break;

      case ClosetSortOption.health:
        sorted.sort((a, b) => b.health.compareTo(a.health));
        break;

      case ClosetSortOption.latest:
        // 등록 시각을 우선 사용하고, 시각이 없는 옛 항목끼리는
        // 이전처럼 목록 위치(뒤쪽일수록 최신)로 정렬합니다.
        final indexMap = <Clothes, int>{};
        for (int i = 0; i < originalOrder.length; i++) {
          indexMap[originalOrder[i]] = i;
        }
        sorted.sort((a, b) {
          final byRecency = Clothes.compareByRecency(a, b);
          if (byRecency != 0) return byRecency;

          final aIndex = indexMap[a] ?? 0;
          final bIndex = indexMap[b] ?? 0;
          return bIndex.compareTo(aIndex);
        });
        break;

      case ClosetSortOption.custom:
        break;
    }

    return sorted;
  }

  /// 제목·분류·관리 지침·소재 이름에서 검색어와 일치하는 의류만 남깁니다.
  List<Clothes> _filterClothes(List<Clothes> source) {
    if (_searchQuery.isEmpty) return source;

    return source.where(_matchesSearch).toList();
  }

  bool _matchesSearch(Clothes item) {
    final searchTargets = [
      item.title,
      item.category,
      item.careInstruction,
      ...item.materials.keys,
    ];

    return searchTargets.any(
      (target) => target.toLowerCase().contains(_searchQuery),
    );
  }

  /// 검색 중인 빈 목록에는 사용자가 입력한 검색어를 함께 표시합니다.
  String _emptyMessage(String defaultMessage) {
    if (_searchQuery.isEmpty) return defaultMessage;

    return '"${_searchController.text.trim()}"에 맞는 의류가 없습니다.';
  }

  /// 길게 누른 항목을 선택하고 순서 변경 모드는 종료합니다.
  void _enterSelectionMode(Clothes item) {
    _updateState(() {
      _reorderMode = false;
      _selectedItems.add(item);
    });
  }

  /// 항목 선택을 전환합니다. 선택이 모두 해제되면 선택 모드도 함께 끝납니다.
  void _toggleSelection(Clothes item) {
    _updateState(() {
      if (_selectedItems.contains(item)) {
        _selectedItems.remove(item);
      } else {
        _selectedItems.add(item);
      }
    });
  }

  /// 선택 상태를 모두 초기화합니다.
  void _exitSelectionMode() {
    _updateState(() {
      _selectedItems.clear();
    });
  }

  /// 확인 후 선택한 의류를 Provider에서 한 번에 삭제합니다.
  Future<void> _deleteSelectedItems() async {
    if (_selectedItems.isEmpty) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        final isDark = Theme.of(dialogContext).brightness == Brightness.dark;
        final palette = AppPalette.of(dialogContext);

        return AlertDialog(
          backgroundColor: palette.card,
          title: Text(
            '선택한 의류 삭제',
            style: TextStyle(
              color: palette.textPrimary,
            ),
          ),
          content: Text(
            '${_selectedItems.length}개의 의류를 삭제할까요?\n이 작업은 되돌릴 수 없습니다.',
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

    if (confirmed != true || !mounted) return;

    final targets = _selectedItems.toList();
    final deleteCount = targets.length;

    try {
      await context.read<ClosetProvider>().removeClothesBatch(targets);
    } catch (_) {
      if (!mounted) return;

      // 삭제 대기 중 빌드 정리가 선택 집합을 비웠을 수 있으므로,
      // 되돌아온 항목 기준으로 선택 상태를 복원해 바로 재시도할 수 있게 합니다.
      final restoredItems = context.read<ClosetProvider>().items;
      _updateState(() {
        _selectedItems
          ..clear()
          ..addAll(targets.where(restoredItems.contains));
      });

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('의류 삭제를 저장하지 못했어요. 다시 시도해 주세요.')),
      );
      return;
    }

    if (!mounted) return;

    _updateState(() {
      _selectedItems.clear();
    });

    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text('$deleteCount개의 의류가 삭제되었습니다.')));
  }

  /// 순서 변경 모드와 다중 선택 모드가 동시에 켜지지 않게 전환합니다.
  void _toggleReorderMode() {
    _updateState(() {
      _reorderMode = !_reorderMode;
      if (_reorderMode) {
        _selectedItems.clear();
      }
    });
  }

  /// 보이는 항목만 재정렬해도 숨겨진 항목의 상대 위치는 그대로 보존합니다.
  Future<void> _handleReorder({
    required List<Clothes> displayedItems,
    required List<Clothes> originalOrder,
    required int oldIndex,
    required int newIndex,
  }) async {
    final reorderedDisplayed = List<Clothes>.from(displayedItems);

    if (newIndex > oldIndex) {
      newIndex -= 1;
    }

    final movedItem = reorderedDisplayed.removeAt(oldIndex);
    reorderedDisplayed.insert(newIndex, movedItem);

    List<Clothes> newGlobalOrder;

    if (displayedItems.length == originalOrder.length) {
      newGlobalOrder = reorderedDisplayed;
    } else {
      final displayedSet = displayedItems.toSet();
      final replacementQueue = List<Clothes>.from(reorderedDisplayed);

      newGlobalOrder = originalOrder.map((item) {
        if (displayedSet.contains(item)) {
          return replacementQueue.removeAt(0);
        }
        return item;
      }).toList();
    }

    try {
      await context.read<ClosetProvider>().setCustomOrder(newGlobalOrder);
    } catch (_) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('변경한 순서를 저장하지 못했어요. 다시 시도해 주세요.')),
      );
    }
  }

}
