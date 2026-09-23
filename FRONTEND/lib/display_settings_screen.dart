// 블랙·화이트·시스템 화면 테마, 하단 메뉴 불투명도, 소재 이름 표시 언어를 선택하는 설정 화면입니다.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'material_name_display_provider.dart';
import 'models/material_name_display.dart';
import 'navigation_bar_opacity_provider.dart';
import 'theme/app_palette.dart';
import 'theme_provider.dart';
import 'utils/material_name.dart';
import 'widgets/app_back_button.dart';
import 'widgets/frosted_surface.dart';

/// [ThemeProvider]·[NavigationBarOpacityProvider]·[MaterialNameDisplayProvider]의 현재 값을
/// 표시하고 사용자의 선택을 전달합니다.
class DisplaySettingsScreen extends StatelessWidget {
  const DisplaySettingsScreen({super.key});

  // 저장 실패를 사용자에게 알리고 불투명도는 Provider가 마지막 저장값으로 되돌립니다.
  Future<void> _applyNavigationBarOpacity(
    BuildContext context,
    NavigationBarOpacityProvider navigationBarOpacityProvider,
    double opacity,
  ) async {
    final messenger = ScaffoldMessenger.of(context);

    try {
      await navigationBarOpacityProvider.setOpacity(opacity);
    } catch (_) {
      messenger.showSnackBar(
        const SnackBar(content: Text('하단 메뉴 설정을 저장하지 못했어요. 다시 시도해 주세요.')),
      );
    }
  }

  // 저장 실패를 사용자에게 알리고 테마는 Provider가 이전 값으로 되돌립니다.
  Future<void> _applyThemeMode(
    BuildContext context,
    ThemeProvider themeProvider,
    ThemeMode mode,
  ) async {
    final messenger = ScaffoldMessenger.of(context);

    try {
      await themeProvider.setThemeMode(mode);
    } catch (_) {
      messenger.showSnackBar(
        const SnackBar(content: Text('테마 설정을 저장하지 못했어요. 다시 시도해 주세요.')),
      );
    }
  }

  // 저장 실패를 사용자에게 알리고 표시 언어는 Provider가 이전 값으로 되돌립니다.
  Future<void> _applyMaterialNameDisplay(
    BuildContext context,
    MaterialNameDisplayProvider materialNameDisplayProvider,
    MaterialNameDisplay display,
  ) async {
    final messenger = ScaffoldMessenger.of(context);

    try {
      await materialNameDisplayProvider.setDisplay(display);
    } catch (_) {
      messenger.showSnackBar(
        const SnackBar(
          content: Text('소재 이름 표시 설정을 저장하지 못했어요. 다시 시도해 주세요.'),
        ),
      );
    }
  }

  String _modeLabel(ThemeMode mode) {
    switch (mode) {
      case ThemeMode.dark:
        return '블랙';
      case ThemeMode.light:
        return '화이트';
      case ThemeMode.system:
        return '시스템 설정';
    }
  }

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    final currentMode = themeProvider.themeMode;
    final materialNameDisplayProvider = context
        .watch<MaterialNameDisplayProvider>();
    final currentMaterialNameDisplay = materialNameDisplayProvider.display;
    final navigationBarOpacityProvider = context
        .watch<NavigationBarOpacityProvider>();
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final backgroundColor = palette.background;
    final cardColor = palette.card;
    final borderColor = isDark
        ? const Color(0xFF2C2C2E)
        : const Color(0xFFEAEAEA);
    final primaryText = palette.textPrimary;
    final secondaryText = palette.textSecondary;

    return Scaffold(
      backgroundColor: backgroundColor,
      appBar: AppBar(
        backgroundColor: backgroundColor,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        automaticallyImplyLeading: false,
        leadingWidth: 52,
        leading: const Padding(
          padding: EdgeInsets.only(left: 8),
          child: AppBackButton(),
        ),
        title: Text(
          '화면 설정',
          style: TextStyle(
            color: primaryText,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
        children: [
          _ThemeModeTile(
            title: '블랙',
            selected: currentMode == ThemeMode.dark,
            onTap: () => _applyThemeMode(context, themeProvider, ThemeMode.dark),
            preview: const _DarkPreview(),
          ),
          const SizedBox(height: 14),
          _ThemeModeTile(
            title: '화이트',
            selected: currentMode == ThemeMode.light,
            onTap: () =>
                _applyThemeMode(context, themeProvider, ThemeMode.light),
            preview: const _LightPreview(),
          ),
          const SizedBox(height: 14),
          _ThemeModeTile(
            title: '시스템 설정',
            selected: currentMode == ThemeMode.system,
            onTap: () =>
                _applyThemeMode(context, themeProvider, ThemeMode.system),
            preview: const _SystemPreview(),
          ),
          const SizedBox(height: 18),
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: cardColor,
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: borderColor),
            ),
            child: Text(
              '현재 선택: ${_modeLabel(currentMode)}\n시스템 설정을 선택하면 기기 테마에 따라 자동으로 전환됩니다.',
              style: TextStyle(color: secondaryText, fontSize: 14, height: 1.6),
            ),
          ),
          const SizedBox(height: 28),
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 10),
            child: Text(
              '하단 메뉴',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: secondaryText,
              ),
            ),
          ),
          _NavigationBarOpacityCard(
            provider: navigationBarOpacityProvider,
            onChangeEnd: (value) => _applyNavigationBarOpacity(
              context,
              navigationBarOpacityProvider,
              value,
            ),
          ),
          const SizedBox(height: 28),
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 10),
            child: Text(
              '소재 이름 표시',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: secondaryText,
              ),
            ),
          ),
          for (final display in MaterialNameDisplay.values) ...[
            _MaterialNameDisplayTile(
              title: display.label,
              // 예시는 실제 리포트와 같은 변환 함수로 만들어 설정 화면과 리포트가 어긋나지 않게 합니다.
              example: '${MaterialName.displayName('cotton', display)} 80%',
              selected: currentMaterialNameDisplay == display,
              onTap: () => _applyMaterialNameDisplay(
                context,
                materialNameDisplayProvider,
                display,
              ),
            ),
            const SizedBox(height: 10),
          ],
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: cardColor,
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: borderColor),
            ),
            child: Text(
              '리포트에 보이는 소재 이름에 적용되고, 저장된 옷 정보는 바뀌지 않아요.\n서버 소재 표에 없는 이름은 번역하지 않고 그대로 보여 줘요.',
              style: TextStyle(color: secondaryText, fontSize: 14, height: 1.6),
            ),
          ),
        ],
      ),
    );
  }
}

/// 테마 미리보기, 선택 상태, 접근성 정보를 함께 제공하는 선택 항목입니다.
class _ThemeModeTile extends StatelessWidget {
  final String title;
  final bool selected;
  final VoidCallback onTap;
  final Widget preview;

  const _ThemeModeTile({
    required this.title,
    required this.selected,
    required this.onTap,
    required this.preview,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final cardColor = palette.card;
    final borderColor = selected
        ? AppPalette.accent
        : (isDark ? const Color(0xFF2C2C2E) : const Color(0xFFEAEAEA));
    final primaryText = palette.textPrimary;

    return Semantics(
      label: '$title 테마',
      button: true,
      selected: selected,
      child: InkWell(
        borderRadius: BorderRadius.circular(24),
        onTap: onTap,
        child: ExcludeSemantics(
          child: Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: cardColor,
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: borderColor, width: selected ? 1.6 : 1),
            ),
            child: Row(
              children: [
                preview,
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    title,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: primaryText,
                    ),
                  ),
                ),
                Icon(
                  selected
                      ? Icons.radio_button_checked
                      : Icons.radio_button_off,
                  color: selected
                      ? AppPalette.accent
                      : const Color(0xFF5F6368),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 소재 이름 표시 언어와 표시 예시, 선택 상태, 접근성 정보를 함께 제공하는 선택 항목입니다.
class _MaterialNameDisplayTile extends StatelessWidget {
  final String title;
  final String example;
  final bool selected;
  final VoidCallback onTap;

  const _MaterialNameDisplayTile({
    required this.title,
    required this.example,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final cardColor = palette.card;
    final borderColor = selected
        ? AppPalette.accent
        : (isDark ? const Color(0xFF2C2C2E) : const Color(0xFFEAEAEA));

    return Semantics(
      label: '소재 이름 $title, 예: $example',
      button: true,
      selected: selected,
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: ExcludeSemantics(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            decoration: BoxDecoration(
              color: cardColor,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: borderColor, width: selected ? 1.6 : 1),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: palette.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        example,
                        style: TextStyle(
                          fontSize: 14,
                          color: palette.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(
                  selected
                      ? Icons.radio_button_checked
                      : Icons.radio_button_off,
                  color: selected
                      ? AppPalette.accent
                      : const Color(0xFF5F6368),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 하단 메뉴 배경 불투명도를 미리보기와 슬라이더(50~100%, 5% 단위)로 조절하는 카드입니다.
///
/// 슬라이더를 끄는 동안은 [NavigationBarOpacityProvider.preview]로 화면에만 반영하고,
/// 손을 떼면 [onChangeEnd]로 저장합니다. 끄는 내내 저장하면 저장소 쓰기가 수십 번 몰립니다.
class _NavigationBarOpacityCard extends StatelessWidget {
  const _NavigationBarOpacityCard({
    required this.provider,
    required this.onChangeEnd,
  });

  final NavigationBarOpacityProvider provider;
  final ValueChanged<double> onChangeEnd;

  static int _percentOf(double opacity) => (opacity * 100).round();

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final borderColor = isDark
        ? const Color(0xFF2C2C2E)
        : const Color(0xFFEAEAEA);
    final opacity = provider.opacity;
    final percent = _percentOf(opacity);
    final divisions =
        ((NavigationBarOpacityProvider.maxOpacity -
                    NavigationBarOpacityProvider.minOpacity) /
                NavigationBarOpacityProvider.step)
            .round();

    return Container(
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 12),
      decoration: BoxDecoration(
        color: palette.card,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '배경 불투명도',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: palette.textPrimary,
                  ),
                ),
              ),
              // 슬라이더 값을 글자로도 보여 줍니다. 낭독기는 슬라이더 자체가 값을 읽으므로 뺍니다.
              ExcludeSemantics(
                child: Text(
                  '$percent%',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: AppPalette.accent,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _NavigationBarOpacityPreview(opacity: opacity),
          const SizedBox(height: 4),
          MergeSemantics(
            child: Semantics(
              label: '하단 메뉴 배경 불투명도',
              child: Slider(
                value: opacity,
                min: NavigationBarOpacityProvider.minOpacity,
                max: NavigationBarOpacityProvider.maxOpacity,
                divisions: divisions,
                label: '$percent%',
                activeColor: AppPalette.accent,
                semanticFormatterCallback: (value) => '${_percentOf(value)}%',
                onChanged: provider.preview,
                onChangeEnd: onChangeEnd,
              ),
            ),
          ),
          Text(
            // 문장마다 줄을 나눈다. 한 줄이면 폰에서 둘째 문장이 낱말 중간에서 꺾였다(2026-09-23 폰 확인).
            '낮출수록 하단 메뉴 뒤로 화면 내용이 흐리게 비쳐요.\n100%는 비치지 않아요.',
            style: TextStyle(
              color: palette.textSecondary,
              fontSize: 13,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }
}

// 하단 메뉴 뒤로 내용이 비치는 정도를 보여 주는 축소 미리보기입니다. 실제 바와 같은 바탕 위젯을 씁니다.
class _NavigationBarOpacityPreview extends StatelessWidget {
  const _NavigationBarOpacityPreview({required this.opacity});

  final double opacity;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final lineColor = palette.textPrimary.withValues(alpha: 0.55);

    return ExcludeSemantics(
      child: Container(
        height: 112,
        decoration: BoxDecoration(
          color: palette.background,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: palette.border),
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          children: [
            // 바 뒤로 스크롤된 글줄과 카드를 흉내 냅니다.
            Positioned(
              left: 18,
              top: 16,
              child: _PreviewBlock(width: 128, height: 10, color: lineColor),
            ),
            Positioned(
              left: 18,
              top: 34,
              child: _PreviewBlock(width: 84, height: 10, color: lineColor),
            ),
            // 카드는 바보다 좁고 아래로 길게 두어, 바 위로 윗변만 살짝 보이고 나머지는
            // 바 뒤로 들어간 모습이 되게 합니다. 바 밖으로 옆변이 나오면 흐림이 안 된
            // 가장자리가 테두리처럼 보입니다(2026-09-23 시뮬레이터 확인).
            Positioned(
              left: 40,
              right: 40,
              top: 44,
              height: 80,
              child: _PreviewBlock(
                height: 80,
                color: AppPalette.accent.withValues(alpha: 0.85),
              ),
            ),
            Positioned(
              left: 16,
              right: 16,
              bottom: 12,
              height: 44,
              child: FrostedSurface(
                opacity: opacity,
                color: palette.card,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: palette.border),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    Icon(Icons.home, color: AppPalette.accent, size: 20),
                    Container(
                      width: 30,
                      height: 30,
                      decoration: const BoxDecoration(
                        color: AppPalette.accent,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        Icons.camera_alt,
                        color: Colors.white,
                        size: 16,
                      ),
                    ),
                    Icon(
                      Icons.checkroom_outlined,
                      color: palette.textSecondary,
                      size: 20,
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
}

class _PreviewBlock extends StatelessWidget {
  const _PreviewBlock({
    this.width,
    required this.height,
    required this.color,
  });

  final double? width;
  final double height;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(6),
      ),
    );
  }
}

// 다크 테마의 축소 미리보기입니다.
class _DarkPreview extends StatelessWidget {
  const _DarkPreview();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 72,
      height: 120,
      decoration: BoxDecoration(
        color: const Color(0xFF25262B),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF1C1C1E)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          children: [
            Container(height: 8, width: 28, color: const Color(0xFF4A4A4A)),
            const SizedBox(height: 8),
            Container(
              height: 22,
              width: double.infinity,
              color: const Color(0xFF3A3A3A),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: Container(height: 18, color: const Color(0xFF444444)),
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: Container(height: 18, color: const Color(0xFF444444)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// 라이트 테마의 축소 미리보기입니다.
class _LightPreview extends StatelessWidget {
  const _LightPreview();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 72,
      height: 120,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE2E2E2)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          children: [
            Container(height: 8, width: 28, color: const Color(0xFFDADADA)),
            const SizedBox(height: 8),
            Container(
              height: 22,
              width: double.infinity,
              color: const Color(0xFFECECEC),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: Container(height: 18, color: const Color(0xFFE7E7E7)),
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: Container(height: 18, color: const Color(0xFFE7E7E7)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// 시스템 설정에 따라 두 테마가 전환됨을 표현하는 미리보기입니다.
class _SystemPreview extends StatelessWidget {
  const _SystemPreview();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 72,
      height: 120,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE2E2E2)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: Column(
          children: [
            Expanded(
              child: Container(
                color: Colors.white,
                child: const Center(
                  child: Icon(Icons.light_mode_outlined, color: Colors.black54),
                ),
              ),
            ),
            Expanded(
              child: Container(
                color: const Color(0xFF25262B),
                child: const Center(
                  child: Icon(Icons.dark_mode_outlined, color: Colors.white70),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
