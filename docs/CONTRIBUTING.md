# Contributing to CloudLeecher

Thank you for your interest in contributing to CloudLeecher! This document provides guidelines and instructions for contributing.

## 🌟 Ways to Contribute

### 1. Report Bugs 🐛
- Check [existing issues](https://github.com/heavens7above/CloudLeecher/issues) first
- Use the bug report template
- Include steps to reproduce, expected vs actual behavior
- Add screenshots if applicable

### 2. Suggest Features 💡
- Open a [feature request](https://github.com/heavens7above/CloudLeecher/issues/new)
- Explain the use case and benefit
- Consider implementation complexity

### 3. Improve Documentation 📝
- Fix typos, improve clarity
- Add examples
- Translate documentation
- Update outdated information

### 4. Submit Code 💻
- Fix bugs
- Implement features
- Improve performance
- Add tests

---

## 🚀 Getting Started

### 1. Fork the Repository

Click the "Fork" button on the [CloudLeecher repository](https://github.com/heavens7above/CloudLeecher)

### 2. Clone Your Fork

```bash
git clone https://github.com/YOUR_USERNAME/CloudLeecher.git
cd CloudLeecher
```

### 3. Add Upstream Remote

```bash
git remote add upstream https://github.com/heavens7above/CloudLeecher.git
```

### 4. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bugfix-name
```

---

## 📋 Development Guidelines

### Code Style

**Frontend (JavaScript/React):**
- Use functional components and hooks
- Follow existing TailwindCSS patterns
- Use meaningful variable names
- Add comments for complex logic

**Backend (Python):**
- Follow PEP 8
- Use type hints where helpful
- Use the `log()` function for logging
- Handle exceptions properly

### Commit Messages

Follow conventional commits:

```
type(scope): subject

body (optional)

footer (optional)
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation changes
- `style` - Code style changes (formatting, etc.)
- `refactor` - Code refactoring
- `perf` - Performance improvements
- `test` - Adding tests
- `chore` - Maintenance tasks

**Examples:**
```
feat(frontend): add dark mode toggle
fix(backend): resolve GID tracking issue
docs: update quick start guide
refactor(api): simplify error handling
```

---

## 🔄 Contribution Workflow

### 1. Keep Your Fork Updated

```bash
git fetch upstream
git checkout main
git merge upstream/main
```

### 2. Make Changes

- Write clean, readable code
- Follow existing patterns
- Test your changes thoroughly

### 3. Test Locally

**Frontend:**
```bash
cd frontend
npm install
npm run dev
npm run build  # Ensure builds successfully
```

**Backend:**
```bash
cd backend
python app.py  # Test locally
# Then test in Google Colab
```

### 4. Commit Changes

```bash
git add .
git commit -m "feat(scope): description"
```

### 5. Push to Your Fork

```bash
git push origin feature/your-feature-name
```

### 6. Create Pull Request

1. Go to your fork on GitHub
2. Click "Compare & pull request"
3. Fill out the PR template
4. Describe your changes clearly
5. Link related issues

---

## ✅ Pull Request Checklist

Before submitting a PR, ensure:

- [ ] Code follows the style guidelines
- [ ] Changes are tested locally
- [ ] Frontend builds without errors (`npm run build`)
- [ ] Backend runs without errors
- [ ] Commit messages follow conventions
- [ ] Documentation updated (if needed)
- [ ] No unnecessary files included
- [ ] PR description is clear and complete

---

## 🎯 Priority Areas

We especially welcome contributions in these areas:

### High Priority
- Bug fixes
- Performance improvements
- Documentation improvements
- Accessibility enhancements

### Medium Priority
- New features (discuss first)
- UI/UX improvements
- Code refactoring
- Test coverage

### Future Enhancements
- Multi-user support
- Download history
- Email notifications
- Mobile app
- Better error recovery

---

## 📦 Project-Specific Guidelines

### Frontend Changes

**Adding Components:**
```
frontend/src/components/
  ui/          # Reusable UI primitives
  layout/      # Layout components
  
frontend/src/features/
  {feature}/   # Feature-specific components
```

**State Management:**
- Use Context API for global state
- Keep component state local when possible
- Avoid prop drilling

**Styling:**
- Use TailwindCSS utility classes
- Follow existing design tokens
- Maintain responsive design

### Backend Changes

**API Endpoints:**
- Document in [API_REFERENCE.md](./API_REFERENCE.md)
- Use consistent error responses
- Add logging for operations
- Validate input data

**Colab Sync:**
- Update both `app.py` and `CloudLeecher.ipynb`
- Keep Cell 4 (%%writefile) in sync with app.py
- Test in actual Colab environment

---

## 🧪 Testing Guidelines

### Frontend Testing
```bash
# Run linter
npm run lint

# Manual testing
npm run dev
# Test all features in browser
```

### Backend Testing
```bash
# Test API endpoints
curl http://localhost:5000/health

# Test in Colab
# Run all notebook cells
# Verify ngrok tunnel works
# Test full download flow
```

### Integration Testing
- Test frontend with backend
- Verify API communication
- Check error handling
- Test edge cases

---

## 🐛 Bug Report Template

When reporting bugs, include:

**Environment:**
- Browser: (Chrome 120, Firefox 121, etc.)
- OS: (macOS 14, Windows 11, etc.)
- Colab tier: (Free, Pro)

**Steps to Reproduce:**
1. Go to...
2. Click on...
3. See error...

**Expected Behavior:**
What should happen

**Actual Behavior:**
What actually happens

**Screenshots:**
If applicable

**Logs:**
- Browser console errors
- Backend logs from Colab or logs panel

---

## 💡 Feature Request Template

When suggesting features, include:

**Summary:**
Brief description

**Motivation:**
Why is this needed? What problem does it solve?

**Proposed Solution:**
How should it work?

**Alternatives:**
Other solutions you considered

**Additional Context:**
Mockups, examples, etc.

---

## 📜 Code of Conduct

### Our Standards

- Be respectful and inclusive
- Welcome newcomers
- Accept constructive criticism
- Focus on what's best for the community
- Show empathy towards others

### Unacceptable Behavior

- Harassment or discrimination
- Trolling or insulting comments
- Personal or political attacks
- Publishing others' private information

---

## 🔒 Security Issues

**DO NOT** open public issues for security vulnerabilities.

Instead:
- Email: [Create secure disclosure]
- Or use GitHub Security Advisory

We'll respond within 48 hours.

---

## 📄 License

By contributing to CloudLeecher, you agree that your contributions will be licensed under the MIT License.

---

## 🙏 Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in commits

---

## ❓ Questions?

- **General Questions**: [GitHub Discussions](https://github.com/heavens7above/CloudLeecher/discussions)
- **Bug Reports**: [GitHub Issues](https://github.com/heavens7above/CloudLeecher/issues)
- **Feature Requests**: [GitHub Issues](https://github.com/heavens7above/CloudLeecher/issues)

---

## 📚 Resources

- [Development Setup](./DEVELOPMENT.md)
- [Architecture](./ARCHITECTURE.md)
- [API Reference](./API_REFERENCE.md)
- [Troubleshooting](./TROUBLESHOOTING.md)

---

**Thank you for contributing to CloudLeecher! 🌩️**
