import 'dart:async';

import 'package:flutter/material.dart';

import '../services/material_catalog_api_service.dart';
import '../services/material_catalog_controller.dart';
import '../theme/app_palette.dart';
import '../utils/material_name.dart';

/// 소재 선택창을 열고 고른 소재를 반환합니다. 고르지 않고 닫으면 null입니다.
///
/// 입력란 아래에 뜨는 추천 목록과 달리 시트가 키보드 높이만큼 올라가 목록이 가려지지 않고,
/// 전체 소재를 스크롤해 볼 수 있습니다. [initialQuery]는 입력란에 적어 둔 글자입니다.
/// [excludedNames]는 다른 줄에 이미 넣은 소재명으로, 목록에서 뺍니다([excludeMaterialCatalog]).
Future<MaterialCatalogItem?> showMaterialPickerSheet({
  required BuildContext context,
  required MaterialCatalogController catalog,
  String initialQuery = '',
  Iterable<String> excludedNames = const [],
}) {
  final isDark = Theme.of(context).brightness == Brightness.dark;

  return showModalBottomSheet<MaterialCatalogItem>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    backgroundColor: isDark ? const Color(0xFF121212) : Colors.white,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    clipBehavior: Clip.antiAlias,
    builder: (sheetContext) {
      return MaterialPickerSheet(
        catalog: catalog,
        initialQuery: initialQuery,
        excludedNames: excludedNames,
        onSelected: (item) {
          Navigator.pop(sheetContext, item);
        },
      );
    },
  );
}

/// 다른 줄에 이미 넣은 소재를 목록에서 뺍니다.
///
/// 같은 소재인지는 글자가 아니라 표준명으로 봅니다(면 = 코튼 = cotton,
/// [MaterialName.standardize]). 항목의 한글명·영문명·별칭 중 하나라도 [excludedNames]의
/// 표준명과 같으면 뺍니다. 빈 이름은 무시하고, 뺄 것이 없으면 목록을 그대로 돌려줍니다.
List<MaterialCatalogItem> excludeMaterialCatalog(
  List<MaterialCatalogItem> items,
  Iterable<String> excludedNames,
) {
  final excludedStandardNames = {
    for (final name in excludedNames)
      if (name.trim().isNotEmpty) MaterialName.standardize(name),
  };
  if (excludedStandardNames.isEmpty) return items;

  bool isExcluded(MaterialCatalogItem item) {
    final names = [item.nameKo, item.nameEn, ...item.aliases];
    return names.any(
      (name) => excludedStandardNames.contains(MaterialName.standardize(name)),
    );
  }

  return [
    for (final item in items)
      if (!isExcluded(item)) item,
  ];
}

/// 검색어로 소재를 거르고, 이름·별칭이 검색어와 같은 것 → 검색어로 시작하는 것 →
/// 검색어를 포함하는 것 순으로 정렬합니다.
///
/// 같은 순위 안에서는 카탈로그 순서를 유지하고, 검색어가 비어 있으면 전체를 그대로 반환합니다.
/// 거르는 기준(대소문자 무시 부분 일치)은 [MaterialCatalogItem.matches]와 같습니다.
List<MaterialCatalogItem> rankMaterialCatalog(
  List<MaterialCatalogItem> items,
  String query,
) {
  final normalizedQuery = query.trim().toLowerCase();
  if (normalizedQuery.isEmpty) return items;

  int? rankOf(MaterialCatalogItem item) {
    final names = [
      item.nameKo,
      item.nameEn,
      ...item.aliases,
    ].map((name) => name.toLowerCase());

    if (names.any((name) => name == normalizedQuery)) return 0;
    if (names.any((name) => name.startsWith(normalizedQuery))) return 1;
    if (names.any((name) => name.contains(normalizedQuery))) return 2;
    return null;
  }

  final ranked = <(int, int, MaterialCatalogItem)>[];

  for (var index = 0; index < items.length; index++) {
    final rank = rankOf(items[index]);
    if (rank != null) ranked.add((rank, index, items[index]));
  }

  ranked.sort(
    (a, b) => a.$1 != b.$1 ? a.$1.compareTo(b.$1) : a.$2.compareTo(b.$2),
  );

  return [for (final entry in ranked) entry.$3];
}

/// 소재 카탈로그를 검색해 하나를 고르는 바텀 시트입니다.
///
/// 카탈로그를 불러오는 중이거나 실패했으면 안내를 보이고, 실패했을 때는 다시 불러올 수 있습니다.
class MaterialPickerSheet extends StatefulWidget {
  const MaterialPickerSheet({
    super.key,
    required this.catalog,
    required this.onSelected,
    this.initialQuery = '',
    this.excludedNames = const [],
  });

  final MaterialCatalogController catalog;
  final ValueChanged<MaterialCatalogItem> onSelected;

  /// 검색창에 미리 채워 둘 글자입니다.
  final String initialQuery;

  /// 다른 줄에 이미 넣어 목록에서 뺄 소재명입니다.
  final Iterable<String> excludedNames;

  @override
  State<MaterialPickerSheet> createState() => _MaterialPickerSheetState();
}

class _MaterialPickerSheetState extends State<MaterialPickerSheet> {
  late final TextEditingController _queryController = TextEditingController(
    text: widget.initialQuery.trim(),
  );

  @override
  void initState() {
    super.initState();

    // 한 번도 요청하지 않은 목록이면 열 때 요청합니다. 빌드 중에 알림이 나가지 않도록
    // 첫 빌드 뒤로 미룹니다. 실패한 목록은 안내와 함께 사용자가 다시 불러오게 둡니다.
    if (widget.catalog.status == MaterialCatalogStatus.idle) {
      scheduleMicrotask(widget.catalog.load);
    }
  }

  @override
  void dispose() {
    _queryController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final primaryText = palette.textPrimary;
    final secondaryText = palette.textSecondary;
    final inputFillColor = isDark ? const Color(0xFF2A2A2E) : Colors.white;
    final maxSheetHeight = MediaQuery.sizeOf(context).height * 0.78;
    final hasExcludedNames = widget.excludedNames.any(
      (name) => name.trim().isNotEmpty,
    );

    return SafeArea(
      top: false,
      child: AnimatedPadding(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        padding: EdgeInsets.only(
          bottom: MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: maxSheetHeight),
          child: ListenableBuilder(
            listenable: Listenable.merge([widget.catalog, _queryController]),
            builder: (context, _) {
              return Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Text(
                      '소재 선택',
                      style: TextStyle(
                        color: primaryText,
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Text(
                      hasExcludedNames
                          ? '한글명·영문명·별칭으로 찾을 수 있어요.\n다른 줄에 이미 넣은 소재는 목록에 없어요.'
                          : '한글명·영문명·별칭으로 찾을 수 있어요.',
                      style: TextStyle(
                        color: secondaryText,
                        fontSize: 13,
                        height: 1.5,
                      ),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: TextField(
                      controller: _queryController,
                      style: TextStyle(color: primaryText),
                      textInputAction: TextInputAction.search,
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: inputFillColor,
                        hintText: '예: 면, cotton',
                        hintStyle: TextStyle(color: secondaryText),
                        prefixIcon: const Icon(Icons.search),
                        suffixIcon: _queryController.text.isEmpty
                            ? null
                            : IconButton(
                                onPressed: _queryController.clear,
                                tooltip: '검색어 지우기',
                                icon: const Icon(Icons.close),
                              ),
                        isDense: true,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Flexible(
                    child: _buildResults(
                      primaryText: primaryText,
                      secondaryText: secondaryText,
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  // 불러오기 상태에 따라 안내 또는 검색 결과 목록을 만듭니다.
  Widget _buildResults({
    required Color primaryText,
    required Color secondaryText,
  }) {
    final catalog = widget.catalog;

    switch (catalog.status) {
      case MaterialCatalogStatus.idle:
      case MaterialCatalogStatus.loading:
        return _buildNotice(
          message: '소재 목록을 불러오는 중이에요.',
          secondaryText: secondaryText,
          leading: const SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2.5),
          ),
        );
      case MaterialCatalogStatus.failed:
        return _buildNotice(
          message: '소재 목록을 불러오지 못했어요.\n입력란에 직접 입력하거나 다시 불러와 주세요.',
          secondaryText: secondaryText,
          action: OutlinedButton.icon(
            onPressed: catalog.load,
            icon: const Icon(Icons.refresh),
            label: const Text('다시 불러오기'),
          ),
        );
      case MaterialCatalogStatus.loaded:
        break;
    }

    final query = _queryController.text;
    final available = excludeMaterialCatalog(
      catalog.items,
      widget.excludedNames,
    );
    final results = rankMaterialCatalog(available, query);

    if (results.isEmpty) {
      // 다른 줄 소재를 빼서 비었을 때는 '검색어에 맞는 소재가 없다'고 하면 소재가 어디
      // 갔는지 알 수 없으므로, 그 이유를 말합니다.
      final String message;
      if (catalog.items.isEmpty) {
        message = '등록된 소재가 없어요.\n입력란에 직접 입력해 주세요.';
      } else if (available.isEmpty) {
        message = '남은 소재가 없어요.\n다른 줄에 이미 넣은 소재는 목록에서 빠져요.';
      } else if (rankMaterialCatalog(catalog.items, query).isNotEmpty) {
        message = '검색한 소재는 다른 줄에 이미 넣었어요.\n다른 소재를 찾거나 입력란에 직접 입력해 주세요.';
      } else {
        message = '검색어에 맞는 소재가 없어요.\n입력란에 직접 입력할 수도 있어요.';
      }

      return _buildNotice(message: message, secondaryText: secondaryText);
    }

    return ListView.builder(
      shrinkWrap: true,
      padding: const EdgeInsets.fromLTRB(8, 0, 8, 16),
      itemCount: results.length,
      itemBuilder: (context, index) {
        final item = results[index];

        // ListTile은 한 줄을 소재 이름이 붙은 버튼 하나로 읽히게 합니다.
        return ListTile(
          title: Text(
            item.nameKo,
            style: TextStyle(color: primaryText, fontWeight: FontWeight.w700),
          ),
          subtitle: Text(item.nameEn, style: TextStyle(color: secondaryText)),
          trailing: Icon(Icons.chevron_right, color: secondaryText),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          onTap: () => widget.onSelected(item),
        );
      },
    );
  }

  Widget _buildNotice({
    required String message,
    required Color secondaryText,
    Widget? leading,
    Widget? action,
  }) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (leading != null) ...[leading, const SizedBox(height: 12)],
          Semantics(
            liveRegion: true,
            child: Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(color: secondaryText, fontSize: 14, height: 1.5),
            ),
          ),
          if (action != null) ...[const SizedBox(height: 14), action],
        ],
      ),
    );
  }
}
