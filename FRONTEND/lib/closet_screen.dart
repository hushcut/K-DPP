import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'models/clothes.dart';

enum ClosetSortOption {
  eco,
  health,
  latest,
  custom,
}

class ClosetScreen extends StatefulWidget {
  const ClosetScreen({super.key});

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
        return '사용자 정의';
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
        return AlertDialog(
          title: const Text('선택한 의류 삭제'),
          content: Text(
            '${_selectedItems.length}개의 의류를 삭제할까요?\n삭제 후에는 옷장과 리포트에 반영됩니다.',
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

    final deleteCount = _selectedItems.length;
    await context
        .read<ClosetProvider>()
        .removeClothesBatch(_selectedItems.toList());

    if (!mounted) return;

    setState(() {
      _selectionMode = false;
      _selectedItems.clear();
    });

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$deleteCount개의 의류가 삭제되었습니다.')),
    );
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

    await context.read<ClosetProvider>().setCustomOrder(newGlobalOrder);
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

    return DefaultTabController(
      length: 3,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
            child: _selectionMode
                ? Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${_selectedItems.length}개 선택됨',
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF1A1A1A),
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    TextButton(
                      onPressed: _exitSelectionMode,
                      child: const Text('취소'),
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
                        '삭제',
                        style: TextStyle(color: Colors.white),
                      ),
                    ),
                  ],
                ),
              ],
            )
                : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '홍길동님의 옷장',
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF1A1A1A),
                  ),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (_sortOption == ClosetSortOption.custom)
                      OutlinedButton.icon(
                        onPressed: _toggleReorderMode,
                        icon: Icon(
                          _reorderMode
                              ? Icons.check
                              : Icons.edit_outlined,
                          size: 18,
                        ),
                        label: Text(_reorderMode ? '편집 완료' : '편집'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: const Color(0xFF4A4EFE),
                          side: const BorderSide(
                            color: Color(0xFF4A4EFE),
                          ),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(20),
                          ),
                        ),
                      ),
                    PopupMenuButton<ClosetSortOption>(
                      onSelected: (value) {
                        setState(() {
                          _sortOption = value;
                          if (value != ClosetSortOption.custom) {
                            _reorderMode = false;
                          }
                        });
                      },
                      itemBuilder: (context) => const [
                        PopupMenuItem(
                          value: ClosetSortOption.eco,
                          child: Text('친환경 순'),
                        ),
                        PopupMenuItem(
                          value: ClosetSortOption.health,
                          child: Text('건강도 순'),
                        ),
                        PopupMenuItem(
                          value: ClosetSortOption.latest,
                          child: Text('최신 등록 순'),
                        ),
                        PopupMenuItem(
                          value: ClosetSortOption.custom,
                          child: Text('사용자 정의'),
                        ),
                      ],
                      child: OutlinedButton.icon(
                        onPressed: null,
                        icon: const Icon(Icons.sort, size: 18),
                        label: Text(_sortLabel),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: const Color(0xFF4A4EFE),
                          disabledForegroundColor:
                          const Color(0xFF4A4EFE),
                          side: const BorderSide(
                            color: Color(0xFF4A4EFE),
                          ),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(20),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                if (_sortOption == ClosetSortOption.custom)
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Text(
                      _reorderMode
                          ? '현재 탭에서 드래그해 원하는 순서로 정렬할 수 있습니다.'
                          : '사용자 정의는 내가 원하는 순서대로 직접 정렬할 수 있습니다.',
                      style: const TextStyle(
                        color: Colors.grey,
                        fontSize: 12,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const TabBar(
            labelColor: Color(0xFF4A4EFE),
            unselectedLabelColor: Colors.grey,
            indicatorColor: Color(0xFF4A4EFE),
            indicatorWeight: 3,
            tabs: [
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
                )
                    : _buildClothesList(
                  context,
                  allItems,
                  emptyMessage: '옷장에 등록된 의류가 없습니다.',
                ),
                _sortOption == ClosetSortOption.custom && _reorderMode
                    ? _buildReorderableClothesList(
                  context,
                  topItems,
                  originalOrder,
                  emptyMessage: '상의 목록이 비어있습니다.',
                )
                    : _buildClothesList(
                  context,
                  topItems,
                  emptyMessage: '상의 목록이 비어있습니다.',
                ),
                _sortOption == ClosetSortOption.custom && _reorderMode
                    ? _buildReorderableClothesList(
                  context,
                  bottomItems,
                  originalOrder,
                  emptyMessage: '하의 목록이 비어있습니다.',
                )
                    : _buildClothesList(
                  context,
                  bottomItems,
                  emptyMessage: '하의 목록이 비어있습니다.',
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
      }) {
    if (clothes.isEmpty) {
      return Center(
        child: Text(
          emptyMessage,
          style: const TextStyle(color: Colors.grey),
        ),
      );
    }

    return ReorderableListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: clothes.length,
      onReorder: (oldIndex, newIndex) async {
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
          ),
        );
      },
    );
  }

  Widget _buildClothesList(
      BuildContext context,
      List<Clothes> clothes, {
        required String emptyMessage,
      }) {
    if (clothes.isEmpty) {
      return Center(
        child: Text(
          emptyMessage,
          style: const TextStyle(color: Colors.grey),
        ),
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
        bool isWarning = false,
        bool showDragHandle = false,
        bool disableTap = false,
      }) {
    final isSelected = _selectedItems.contains(item);

    return Container(
      decoration: BoxDecoration(
        color: isSelected
            ? const Color(0xFFEEF1FF)
            : (isWarning ? Colors.red.shade50 : Colors.white),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isSelected
              ? const Color(0xFF4A4EFE)
              : (isWarning
              ? Colors.redAccent.shade200
              : Colors.grey.shade200),
          width: isSelected ? 2 : (isWarning ? 2 : 1),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
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
                ? Colors.white
                : (isWarning ? Colors.white : Colors.grey.shade100),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(
            Icons.checkroom,
            color: isSelected
                ? const Color(0xFF4A4EFE)
                : (isWarning ? Colors.redAccent : Colors.grey),
            size: 30,
          ),
        ),
        title: Text(
          title,
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 8.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                category,
                style: const TextStyle(
                  color: Colors.grey,
                  fontSize: 12,
                ),
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
                        fontWeight:
                        isWarning ? FontWeight.bold : FontWeight.normal,
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
            ? const Icon(Icons.drag_handle, color: Colors.grey)
            : (_selectionMode
            ? Icon(
          isSelected
              ? Icons.check_circle
              : Icons.radio_button_unchecked,
          color: isSelected
              ? const Color(0xFF4A4EFE)
              : Colors.grey,
        )
            : const Icon(Icons.chevron_right, color: Colors.grey)),
        onTap: disableTap
            ? null
            : () {
          if (_selectionMode) {
            _toggleSelection(item);
            return;
          }

          context.read<ClosetProvider>().selectClothes(item);
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