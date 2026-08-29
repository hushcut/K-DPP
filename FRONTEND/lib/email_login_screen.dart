// 이메일·비밀번호 입력을 검증하고 서버 로그인 및 로그인 후 동기화를 수행하는 화면입니다.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'services/auth_api_service.dart';
import 'services/post_login_sync_service.dart';
import 'signup_screen.dart';
import 'theme/app_palette.dart';
import 'widgets/app_back_button.dart';

/// 로그인 요청의 진행 상태와 비밀번호 표시 상태를 관리하는 이메일 로그인 화면입니다.
class EmailLoginScreen extends StatefulWidget {
  const EmailLoginScreen({super.key, this.authApiService});

  final AuthApiService? authApiService;

  @override
  State<EmailLoginScreen> createState() => _EmailLoginScreenState();
}

class _EmailLoginScreenState extends State<EmailLoginScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  late final AuthApiService _authApiService;
  late final PostLoginSyncService _postLoginSyncService;

  bool _isLoading = false;
  bool _obscurePassword = true;
  bool _didLoadInitialEmail = false;

  @override
  void initState() {
    super.initState();
    _authApiService = widget.authApiService ?? AuthApiService();
    _postLoginSyncService = PostLoginSyncService(
      authApiService: _authApiService,
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    if (_didLoadInitialEmail) return;
    _didLoadInitialEmail = true;

    // 회원가입 직후 전달된 이메일이 있으면 로그인 폼에 한 번만 채웁니다.
    final args = ModalRoute.of(context)?.settings.arguments;
    if (args is String && args.trim().isNotEmpty) {
      _emailController.text = args.trim();
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  // 제출 전에 네트워크 요청 없이 기본 입력 형식을 검사합니다.
  String? _validateEmail(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '이메일을 입력해 주세요';
    }

    if (!text.contains('@') || !text.contains('.')) {
      return '올바른 이메일 형식을 입력해 주세요';
    }

    return null;
  }

  String? _validatePassword(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '비밀번호를 입력해 주세요';
    }

    if (text.length < 8) {
      return '비밀번호는 8자 이상 입력해 주세요';
    }

    return null;
  }

  /// 폼 검증 → 서버 로그인 → 세션 저장 → 서버 이력 동기화 순으로 처리합니다.
  Future<void> _handleLogin() async {
    final isValid = _formKey.currentState?.validate() ?? false;
    if (!isValid) return;

    setState(() {
      _isLoading = true;
    });

    try {
      final result = await _authApiService.login(
        email: _emailController.text.trim(),
        password: _passwordController.text,
      );

      if (!mounted) return;

      final provider = context.read<ClosetProvider>();
      final accessToken = result.accessToken!;

      await provider.setAuthenticatedUser(
        nickname: result.user.nickname,
        email: result.user.email,
        accessToken: accessToken,
        expiresInSeconds: result.expiresInSeconds!,
      );

      if (!mounted) return;

      await _postLoginSyncService.synchronize(
        provider: provider,
        accessToken: accessToken,
      );

      if (!mounted) return;

      // 인증 화면으로 돌아오지 않도록 이전 경로를 모두 제거합니다.
      Navigator.pushNamedAndRemoveUntil(context, '/main', (route) => false);
    } on AuthApiException catch (error) {
      if (!mounted) return;

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.userMessage)));
    } catch (error, stackTrace) {
      debugPrint('로그인 세션 저장 중 오류가 발생했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('로그인 정보를 안전하게 저장하지 못했습니다. 다시 시도해 주세요.')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  // 이메일과 비밀번호 입력란에 공통으로 쓰는 테마별 스타일입니다.
  InputDecoration _inputDecoration({
    required String labelText,
    required String hintText,
    Widget? suffixIcon,
  }) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final fillColor = isDark
        ? const Color(0xFF1C1C1E)
        : const Color(0xFFF1F1F4);
    final hintColor = isDark
        ? const Color(0xFF9A9A9A)
        : const Color(0xFF9E9E9E);
    final enabledBorderColor = isDark
        ? const Color(0xFF2C2C2E)
        : Colors.transparent;

    return InputDecoration(
      labelText: labelText,
      hintText: hintText,
      labelStyle: TextStyle(color: hintColor, fontSize: 15),
      hintStyle: TextStyle(color: hintColor, fontSize: 15),
      filled: true,
      fillColor: fillColor,
      contentPadding: const EdgeInsets.symmetric(horizontal: 22, vertical: 22),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(28),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(28),
        borderSide: BorderSide(
          color: enabledBorderColor,
          width: isDark ? 1 : 0,
        ),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(28),
        borderSide: const BorderSide(color: AppPalette.accent, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(28),
        borderSide: const BorderSide(color: Colors.redAccent, width: 1.2),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(28),
        borderSide: const BorderSide(color: Colors.redAccent, width: 1.5),
      ),
      suffixIcon: suffixIcon,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final backgroundColor = palette.background;
    final primaryText = palette.textPrimary;
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF8C8C8C);
    final iconColor = isDark
        ? const Color(0xFFB8B8BE)
        : const Color(0xFF8C8C8C);

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
          '로그인',
          style: TextStyle(
            color: primaryText,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: LayoutBuilder(
            builder: (context, constraints) {
              return SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight: constraints.maxHeight - 12,
                  ),
                  child: IntrinsicHeight(
                    child: Column(
                      children: [
                        const SizedBox(height: 48),
                        Text(
                          'K-DPP에 로그인하세요',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: primaryText,
                          ),
                        ),
                        const SizedBox(height: 10),
                        Text(
                          '계정 정보를 입력하고 서비스를 시작해 보세요.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 14,
                            color: secondaryText,
                            height: 1.5,
                          ),
                        ),
                        const SizedBox(height: 40),
                        TextFormField(
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [
                            AutofillHints.username,
                            AutofillHints.email,
                          ],
                          autocorrect: false,
                          validator: _validateEmail,
                          style: TextStyle(color: primaryText),
                          cursorColor: AppPalette.accent,
                          decoration: _inputDecoration(
                            labelText: '이메일',
                            hintText: 'honggildong@example.com',
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _passwordController,
                          obscureText: _obscurePassword,
                          textInputAction: TextInputAction.done,
                          autofillHints: const [AutofillHints.password],
                          enableSuggestions: false,
                          autocorrect: false,
                          validator: _validatePassword,
                          style: TextStyle(color: primaryText),
                          cursorColor: AppPalette.accent,
                          decoration: _inputDecoration(
                            labelText: '비밀번호',
                            hintText: '8자 이상 입력',
                            suffixIcon: IconButton(
                              onPressed: () {
                                setState(() {
                                  _obscurePassword = !_obscurePassword;
                                });
                              },
                              tooltip: _obscurePassword
                                  ? '비밀번호 표시'
                                  : '비밀번호 숨기기',
                              icon: Icon(
                                _obscurePassword
                                    ? Icons.visibility_off_outlined
                                    : Icons.visibility_outlined,
                                color: iconColor,
                              ),
                            ),
                          ),
                          onFieldSubmitted: (_) {
                            if (!_isLoading) {
                              _handleLogin();
                            }
                          },
                        ),
                        const SizedBox(height: 32),
                        SizedBox(
                          width: double.infinity,
                          height: 60,
                          child: ElevatedButton(
                            onPressed: _isLoading ? null : _handleLogin,
                            style: ElevatedButton.styleFrom(
                              elevation: 0,
                              backgroundColor: AppPalette.accent,
                              disabledBackgroundColor: const Color(0x8C4A4EFE),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(30),
                              ),
                            ),
                            child: _isLoading
                                ? Semantics(
                                    label: '로그인 처리 중',
                                    liveRegion: true,
                                    child: const SizedBox(
                                      width: 22,
                                      height: 22,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2.4,
                                        color: Colors.white,
                                      ),
                                    ),
                                  )
                                : const Text(
                                    '로그인',
                                    style: TextStyle(
                                      fontSize: 20,
                                      fontWeight: FontWeight.w700,
                                      color: Colors.white,
                                    ),
                                  ),
                          ),
                        ),
                        const SizedBox(height: 18),
                        TextButton(
                          onPressed: () async {
                            // 회원가입이 pop으로 돌아오면 이 화면을 재사용하고,
                            // 전달된 이메일이 있으면 로그인 폼에 채웁니다.
                            final result = await Navigator.pushNamed(
                              context,
                              '/signup',
                              arguments: SignupScreen.fromEmailLoginArgument,
                            );

                            if (!mounted ||
                                result is! String ||
                                result.trim().isEmpty) {
                              return;
                            }

                            _emailController.text = result.trim();
                          },
                          style: TextButton.styleFrom(
                            minimumSize: const Size(48, 48),
                          ),
                          child: Text(
                            '계정이 없으신가요? 회원가입',
                            style: TextStyle(
                              color: isDark
                                  ? const Color(0xFFB8B8BE)
                                  : const Color(0xFF5F6368),
                              fontSize: 14,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                        const Spacer(),
                        const SizedBox(height: 24),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}
