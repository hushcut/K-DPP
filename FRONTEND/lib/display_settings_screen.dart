// 블랙·화이트·시스템 화면 테마를 선택하고 미리 보는 설정 화면입니다.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'theme/app_palette.dart';
import 'theme_provider.dart';
import 'widgets/app_back_button.dart';

/// [ThemeProvider]의 현재 모드를 표시하고 사용자의 테마 선택을 전달합니다.
class DisplaySettingsScreen extends StatelessWidget {
  const DisplaySettingsScreen({super.key});

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
