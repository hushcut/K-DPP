import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'services/auth_session_validation_service.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({
    super.key,
    this.authSessionValidationService = const AuthSessionValidationService(),
    this.minimumDisplayDuration = const Duration(milliseconds: 1200),
  });

  final AuthSessionValidationService authSessionValidationService;
  final Duration minimumDisplayDuration;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _fadeAnimation;
  late final Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();

    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );

    _fadeAnimation = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOut,
    );

    _scaleAnimation = Tween<double>(
      begin: 0.96,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));

    _controller.forward();
    _initializeApp();
  }

  Future<void> _initializeApp() async {
    final provider = context.read<ClosetProvider>();
    var shouldOpenMain = false;

    try {
      await provider.loadFromStorage();

      final accessToken = provider.accessToken;

      if (provider.isAuthenticated && accessToken != null) {
        final validation = await widget.authSessionValidationService.validate(
          accessToken: accessToken,
        );

        switch (validation) {
          case AuthSessionValid(:final user, :final history):
            await provider.setUserProfile(
              nickname: user.nickname,
              email: user.email,
            );
            await provider.synchronizeServerHistory(history);
          case AuthSessionInvalid():
            await provider.logout();
          case AuthSessionUnavailable():
            break;
        }
      }

      shouldOpenMain = provider.isAuthenticated;
    } catch (error, stackTrace) {
      debugPrint('앱 초기화 중 오류가 발생했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    }

    await Future.delayed(widget.minimumDisplayDuration);

    if (!mounted) return;

    Navigator.pushReplacementNamed(
      context,
      shouldOpenMain ? '/main' : '/login',
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final backgroundColor = isDark
        ? const Color(0xFF121212)
        : const Color(0xFFF8F9FC);
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);

    return Scaffold(
      backgroundColor: backgroundColor,
      body: Center(
        child: FadeTransition(
          opacity: _fadeAnimation,
          child: ScaleTransition(
            scale: _scaleAnimation,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 84,
                  height: 84,
                  decoration: BoxDecoration(
                    color: const Color(0xFF4A4EFE),
                    borderRadius: BorderRadius.circular(24),
                  ),
                  child: const Icon(
                    Icons.eco_outlined,
                    color: Colors.white,
                    size: 40,
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  'K-DPP',
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    color: primaryText,
                    letterSpacing: -0.5,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
