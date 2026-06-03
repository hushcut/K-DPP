import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'models/clothes.dart';

enum ClosetSortOption { eco, health, latest, custom }

class ClosetScreen extends StatefulWidget {
  const ClosetScreen({super.key, this.onOpenReport});

  final ValueChanged<Clothes>? onOpenReport;

  @override
  State<ClosetScreen> createState() => _ClosetScreenState();
}

class _ClosetScreenState extends State<ClosetScreen> {
  ClosetSortOption _sortOption = ClosetSortOption.eco;
  bool _selectionMode = false;
  bool _reorderMode = false;
  final Set<Clothes> _selectedItems = {};

  String get _sortLabel {
    switch (_sortOption) {
      case ClosetSortOption.eco:
        return '친환경 순';
      case ClosetSortOption.health:
        return '건강도 순';
      case ClosetSortOption.latest:
        return '최신 등록 순';
      case ClosetSortOption.custom:
        return '내설정순';
    }
  }

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
        final indexMap = <Clothes, int>{};
        for (int i = 0; i < originalOrder.length; i++) {
          indexMap[originalOrder[i]] = i;
        }
        sorted.sort((a, b) {
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

  void _enterSelectionMode(Clothes item) {
    setState(() {
      _selectionMode = true;
      _reorderMode = false;
      _selectedItems.add(item);
    });
  }

  void _toggleSelection(Clothes item) {
    setState(() {
      if (_selectedItems.contains(item)) {
        _selectedItems.remove(item);
      } else {
        _selectedItems.add(item);
      }

      if (_selectedItems.isEmpty) {
        _selectionMode = false;
      }
    });
  }

  void _exitSelectionMode() {
    setState(() {
      _selectionMode = false;
      _selectedItems.clear();
    });
  }

  Future<void> _deleteSelectedItems() async {
    if (_selectedItems.isEmpty) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        final isDark = Theme.of(dialogContext).brightness == Brightness.dark;

        return AlertDialog(
          backgroundColor: isDark ? const Color(0xFF1C1C1E) : Colors.white,
          title: Text(
            '선택한 의류 삭제',
            style: TextStyle(
              color: isDark ? Colors.white : const Color(0xFF111111),
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

    if (confirmed != true) return;

    if (!mounted) return;

    final deleteCount = _selectedItems.length;
    await context.read<ClosetProvider>().removeClothesBatch(
      _selectedItems.toList(),
    );

    if (!mounted) return;

    setState(() {
      _selectionMode = false;
      _selectedItems.clear();
    });

    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text('$deleteCount개의 의류가 삭제되었습니다.')));
  }

  void _toggleReorderMode() {
    setState(() {
      _reorderMode = !_reorderMode;
      if (_reorderMode) {
        _selectionMode = false;
        _selectedItems.clear();
      }
    });
  }

  Future<void> _handleReorder({
    required List<Clothes> displayedItems,
    required List<Clothes> originalOrder,
    required int oldIndex,
    required int newIndex,
  }) async {
    final reorderedDisplayed = List<Clothes>.from(displayedItems);

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

    await context.read<ClosetProvider>().setCustomOrder(newGlobalOrder);
  }

  Future<void> _showSortBottomSheet() async {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final sheetColor = isDark ? const Color(0xFF121212) : Colors.white;
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF8C8C8C);

    final selected = await showModalBottomSheet<ClosetSortOption>(
      context: context,
      showDragHandle: true,
      backgroundColor: sheetColor,
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
                  secondaryText: secondaryText,
                  isDark: isDark,
                ),
                _buildSortOptionTile(
                  label: '건강도 순',
                  value: ClosetSortOption.health,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                  isDark: isDark,
                ),
                _buildSortOptionTile(
                  label: '최신 등록 순',
                  value: ClosetSortOption.latest,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                  isDark: isDark,
                ),
                _buildSortOptionTile(
                  label: '내설정순',
                  value: ClosetSortOption.custom,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                  isDark: isDark,
                ),
              ],
            ),
          ),
        );
      },
    );

    if (selected == null) return;

    setState(() {
      _sortOption = selected;
      if (selected != ClosetSortOption.custom) {
        _reorderMode = false;
      }
    });
  }

  Widget _buildSortOptionTile({
    required String label,
    required ClosetSortOption value,
    required Color primaryText,
    required Color secondaryText,
    required bool isDark,
  }) {
    final isSelected = _sortOption == value;

    return InkWell(
      onTap: () => Navigator.pop(context, value),
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: TextStyle(
                  fontSize: 18,
                  color: isSelected ? const Color(0xFF4A4EFE) : primaryText,
                  fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                ),
              ),
            ),
            Icon(
              isSelected ? Icons.check : Icons.radio_button_unchecked,
              color: isSelected ? const Color(0xFF4A4EFE) : secondaryText,
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final clothesList = context.watch<ClosetProvider>().items;
    final originalOrder = clothesList.toList();

    final allItems = _sortClothes(
      List<Clothes>.from(clothesList),
      originalOrder,
    );

    final topItems = _sortClothes(
      clothesList.where((item) => item.category == '상의').toList(),
      originalOrder,
    );

    final bottomItems = _sortClothes(
      clothesList.where((item) => item.category == '하의').toList(),
      originalOrder,
    );

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primaryText = isDark ? Colors.white : const Color(0xFF1A1A1A);
    final secondaryText = isDark ? const Color(0xFFD1D1D6) : Colors.grey;
    final baseCardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor = isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade200;
    final selectedBgColor = isDark
        ? const Color(0xFF232A45)
        : const Color(0xFFEEF1FF);
    final warningBgColor = isDark
        ? const Color(0xFF2A1E1E)
        : Colors.red.shade50;
    final leadingBgColor = isDark
        ? const Color(0xFF2A2A2E)
        : Colors.grey.shade100;
    final shadowColor = isDark
        ? Colors.black.withValues(alpha: 0.16)
        : Colors.black.withValues(alpha: 0.03);

    return DefaultTabController(
      length: 3,
      child: Column(
        children: [
          if (_selectionMode)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${_selectedItems.length}개 선택됨',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: primaryText,
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
                        icon: const Icon(
                          Icons.delete_outline,
                          color: Colors.white,
                        ),
                        label: const Text(
                          '선택 삭제',
                          style: TextStyle(color: Colors.white),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            )
          else
            Padding(
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
                            color: primaryText,
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
                              icon: const Icon(
                                Icons.sort,
                                color: Color(0xFF4A4EFE),
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
                    style: TextStyle(color: secondaryText, fontSize: 13),
                  ),
                  const SizedBox(height: 6),
                  SizedBox(
                    height: 18,
                    child: Text(
                      _sortOption == ClosetSortOption.custom
                          ? (_reorderMode
                                ? '드래그해서 순서를 바꿔 보세요.'
                                : '내설정순으로 정렬되어 있어요.')
                          : '원하는 방식으로 옷장을 정리해 보세요.',
                      style: TextStyle(color: secondaryText, fontSize: 12),
                    ),
                  ),
                ],
              ),
            ),
          TabBar(
            labelColor: const Color(0xFF4A4EFE),
            unselectedLabelColor: secondaryText,
            indicatorColor: const Color(0xFF4A4EFE),
            indicatorWeight: 3,
            tabs: const [
              Tab(text: '전체'),
              Tab(text: '상의'),
              Tab(text: '하의'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: [
                _sortOption == ClosetSortOption.custom && _reorderMode
                    ? _buildReorderableClothesList(
                        context,
                        allItems,
                        originalOrder,
                        emptyMessage: '옷장에 등록된 의류가 없습니다.',
                        primaryText: primaryText,
                        secondaryText: secondaryText,
                        cardColor: baseCardColor,
                        borderColor: borderColor,
                        selectedBgColor: selectedBgColor,
                        warningBgColor: warningBgColor,
                        leadingBgColor: leadingBgColor,
                        shadowColor: shadowColor,
                        isDark: isDark,
                      )
                    : _buildClothesList(
                        context,
                        allItems,
                        emptyMessage: '옷장에 등록된 의류가 없습니다.',
                        primaryText: primaryText,
                        secondaryText: secondaryText,
                        cardColor: baseCardColor,
                        borderColor: borderColor,
                        selectedBgColor: selectedBgColor,
                        warningBgColor: warningBgColor,
                        leadingBgColor: leadingBgColor,
                        shadowColor: shadowColor,
                        isDark: isDark,
                      ),
                _sortOption == ClosetSortOption.custom && _reorderMode
                    ? _buildReorderableClothesList(
                        context,
                        topItems,
                        originalOrder,
                        emptyMessage: '상의 의류가 없습니다.',
                        primaryText: primaryText,
                        secondaryText: secondaryText,
                        cardColor: baseCardColor,
                        borderColor: borderColor,
                        selectedBgColor: selectedBgColor,
                        warningBgColor: warningBgColor,
                        leadingBgColor: leadingBgColor,
                        shadowColor: shadowColor,
                        isDark: isDark,
                      )
                    : _buildClothesList(
                        context,
                        topItems,
                        emptyMessage: '상의 의류가 없습니다.',
                        primaryText: primaryText,
                        secondaryText: secondaryText,
                        cardColor: baseCardColor,
                        borderColor: borderColor,
                        selectedBgColor: selectedBgColor,
                        warningBgColor: warningBgColor,
                        leadingBgColor: leadingBgColor,
                        shadowColor: shadowColor,
                        isDark: isDark,
                      ),
                _sortOption == ClosetSortOption.custom && _reorderMode
                    ? _buildReorderableClothesList(
                        context,
                        bottomItems,
                        originalOrder,
                        emptyMessage: '하의 의류가 없습니다.',
                        primaryText: primaryText,
                        secondaryText: secondaryText,
                        cardColor: baseCardColor,
                        borderColor: borderColor,
                        selectedBgColor: selectedBgColor,
                        warningBgColor: warningBgColor,
                        leadingBgColor: leadingBgColor,
                        shadowColor: shadowColor,
                        isDark: isDark,
                      )
                    : _buildClothesList(
                        context,
                        bottomItems,
                        emptyMessage: '하의 의류가 없습니다.',
                        primaryText: primaryText,
                        secondaryText: secondaryText,
                        cardColor: baseCardColor,
                        borderColor: borderColor,
                        selectedBgColor: selectedBgColor,
                        warningBgColor: warningBgColor,
                        leadingBgColor: leadingBgColor,
                        shadowColor: shadowColor,
                        isDark: isDark,
                      ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildReorderableClothesList(
    BuildContext context,
    List<Clothes> clothes,
    List<Clothes> originalOrder, {
    required String emptyMessage,
    required Color primaryText,
    required Color secondaryText,
    required Color cardColor,
    required Color borderColor,
    required Color selectedBgColor,
    required Color warningBgColor,
    required Color leadingBgColor,
    required Color shadowColor,
    required bool isDark,
  }) {
    if (clothes.isEmpty) {
      return Center(
        child: Text(emptyMessage, style: TextStyle(color: secondaryText)),
      );
    }

    return ReorderableListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: clothes.length,
      onReorderItem: (oldIndex, newIndex) async {
        await _handleReorder(
          displayedItems: clothes,
          originalOrder: originalOrder,
          oldIndex: oldIndex,
          newIndex: newIndex,
        );
      },
      itemBuilder: (context, index) {
        final item = clothes[index];
        return Padding(
          key: ValueKey(item),
          padding: const EdgeInsets.only(bottom: 12.0),
          child: _buildClosetItem(
            context,
            item: item,
            title: item.title,
            category: item.category,
            status: item.health > 20
                ? '건강 상태: ${item.health}%'
                : '수명 만료 (배출 권장)',
            statusColor: item.health > 20 ? Colors.green : Colors.redAccent,
            statusIcon: item.health > 20
                ? Icons.sentiment_satisfied_alt
                : Icons.warning_amber_rounded,
            isWarning: item.health <= 20,
            showDragHandle: true,
            disableTap: true,
            primaryText: primaryText,
            secondaryText: secondaryText,
            cardColor: cardColor,
            borderColor: borderColor,
            selectedBgColor: selectedBgColor,
            warningBgColor: warningBgColor,
            leadingBgColor: leadingBgColor,
            shadowColor: shadowColor,
            isDark: isDark,
          ),
        );
      },
    );
  }

  Widget _buildClothesList(
    BuildContext context,
    List<Clothes> clothes, {
    required String emptyMessage,
    required Color primaryText,
    required Color secondaryText,
    required Color cardColor,
    required Color borderColor,
    required Color selectedBgColor,
    required Color warningBgColor,
    required Color leadingBgColor,
    required Color shadowColor,
    required bool isDark,
  }) {
    if (clothes.isEmpty) {
      return Center(
        child: Text(emptyMessage, style: TextStyle(color: secondaryText)),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: clothes.length,
      itemBuilder: (context, index) {
        final item = clothes[index];

        return Padding(
          padding: const EdgeInsets.only(bottom: 12.0),
          child: _buildClosetItem(
            context,
            item: item,
            title: item.title,
            category: item.category,
            status: item.health > 20
                ? '건강 상태: ${item.health}%'
                : '수명 만료 (배출 권장)',
            statusColor: item.health > 20 ? Colors.green : Colors.redAccent,
            statusIcon: item.health > 20
                ? Icons.sentiment_satisfied_alt
                : Icons.warning_amber_rounded,
            isWarning: item.health <= 20,
            primaryText: primaryText,
            secondaryText: secondaryText,
            cardColor: cardColor,
            borderColor: borderColor,
            selectedBgColor: selectedBgColor,
            warningBgColor: warningBgColor,
            leadingBgColor: leadingBgColor,
            shadowColor: shadowColor,
            isDark: isDark,
          ),
        );
      },
    );
  }

  Widget _buildClosetItem(
    BuildContext context, {
    required Clothes item,
    required String title,
    required String category,
    required String status,
    required Color statusColor,
    required IconData statusIcon,
    required Color primaryText,
    required Color secondaryText,
    required Color cardColor,
    required Color borderColor,
    required Color selectedBgColor,
    required Color warningBgColor,
    required Color leadingBgColor,
    required Color shadowColor,
    required bool isDark,
    bool isWarning = false,
    bool showDragHandle = false,
    bool disableTap = false,
  }) {
    final isSelected = _selectedItems.contains(item);

    return Container(
      decoration: BoxDecoration(
        color: isSelected
            ? selectedBgColor
            : (isWarning ? warningBgColor : cardColor),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isSelected
              ? const Color(0xFF4A4EFE)
              : (isWarning ? Colors.redAccent.shade200 : borderColor),
          width: isSelected ? 2 : (isWarning ? 2 : 1),
        ),
        boxShadow: [
          BoxShadow(
            color: shadowColor,
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: Container(
          width: 60,
          height: 60,
          decoration: BoxDecoration(
            color: isSelected
                ? (isDark ? const Color(0xFF1C1C1E) : Colors.white)
                : (isWarning
                      ? (isDark ? const Color(0xFF1C1C1E) : Colors.white)
                      : leadingBgColor),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(
            Icons.checkroom,
            color: isSelected
                ? const Color(0xFF4A4EFE)
                : (isWarning ? Colors.redAccent : secondaryText),
            size: 30,
          ),
        ),
        title: Text(
          title,
          style: TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 16,
            color: primaryText,
          ),
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 8.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                category,
                style: TextStyle(color: secondaryText, fontSize: 12),
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Icon(statusIcon, color: statusColor, size: 16),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      status,
                      style: TextStyle(
                        color: statusColor,
                        fontWeight: isWarning
                            ? FontWeight.bold
                            : FontWeight.normal,
                        fontSize: 13,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        trailing: showDragHandle
            ? Icon(Icons.drag_handle, color: secondaryText)
            : (_selectionMode
                  ? Icon(
                      isSelected
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      color: isSelected
                          ? const Color(0xFF4A4EFE)
                          : secondaryText,
                    )
                  : Icon(Icons.chevron_right, color: secondaryText)),
        onTap: disableTap
            ? null
            : () {
                if (_selectionMode) {
                  _toggleSelection(item);
                  return;
                }

                context.read<ClosetProvider>().selectClothes(item);

                if (widget.onOpenReport != null) {
                  widget.onOpenReport!(item);
                  return;
                }

                Navigator.pushNamed(context, '/report', arguments: item);
              },
        onLongPress: disableTap
            ? null
            : () {
                if (_selectionMode) {
                  _toggleSelection(item);
                  return;
                }
                _enterSelectionMode(item);
              },
      ),
    );
  }
}
