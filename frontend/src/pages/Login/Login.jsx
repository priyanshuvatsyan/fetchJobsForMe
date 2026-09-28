import React, { useState } from 'react';
import './Login.css';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [activeTab, setActiveTab] = useState('login');

  const handleSubmit = (e) => {
    e.preventDefault();
    console.log('Logging in with:', { email, password });
  };

  return (
    <div className="login-layout">
      {/* Decorative Background Elements */}
      <div className="blob blob-1"></div>
      <div className="blob blob-2"></div>

      <div className="login-split-container">
        {/* Left Side: Data & System Status */}
        <div className="system-info-panel">
          <div className="panel-header">
            <div className="status-indicator">
              <span className="pulse-dot"></span>
              Agent Gateway Online
            </div>
            <div className="environment-badge">V 1.0</div>
          </div>

          <div className="hero-text">
            <h1>Fetch Jobs For Me</h1>
            <p>Your personal AI agent for autonomous job hunting, smart applications, and automated email handling.</p>
          </div>

          {/* Replaced metrics with practical Pre-Login Features */}
          <div className="features-grid">
            <div className="feature-card fade-in-delay-1">
              <div className="feature-icon search-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8"></circle>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
              </div>
              <div className="feature-text">
                <h3>Smart Scraping</h3>
                <p>Monitors 50+ job portals 24/7 for roles matching your exact skills.</p>
              </div>
            </div>
            
            <div className="feature-card fade-in-delay-2">
              <div className="feature-icon apply-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 2L11 13M22 2L15 22L11 13L2 9L22 2Z"></path>
                </svg>
              </div>
              <div className="feature-text">
                <h3>Tailored Applications</h3>
                <p>Generates custom cover letters and executes 1-click applies autonomously.</p>
              </div>
            </div>
            
            <div className="feature-card fade-in-delay-3">
              <div className="feature-icon email-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
                  <polyline points="22,6 12,13 2,6"></polyline>
                </svg>
              </div>
              <div className="feature-text">
                <h3>Inbox Sync</h3>
                <p>Automatically flags interview invites and filters out rejection noise.</p>
              </div>
            </div>
          </div>

          <div className="terminal-window fade-in-delay-4">
            <div className="terminal-header">
              <span className="dot red"></span>
              <span className="dot yellow"></span>
              <span className="dot green"></span>
              <span className="terminal-title">agent-core_tail</span>
            </div>
            <div className="terminal-body">
              <p className="log-line"><span>[INFO]</span> Booting up autonomous job-fetcher engine...</p>
              <p className="log-line"><span>[INFO]</span> Establishing secure connection to job portal APIs...</p>
              <p className="log-line"><span>[INFO]</span> Ready to scan for DevOps Engineer and related roles.</p>
              <p className="log-line"><span>[WARN]</span> User unauthenticated. Operations paused.</p>
              <p className="log-line animate-type"><span>[SYS]</span> Awaiting user authentication to commence hunt...<span className="cursor">_</span></p>
            </div>
          </div>
        </div>

        {/* Right Side: Enhanced Login Form */}
        <div className="login-form-panel">
          <div className="form-card">
            <div className="login-header">
              <div className="logo-icon float-animation">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M20 7L12 3L4 7M20 7L12 11M20 7V17L12 21M12 11L4 7M12 11V21M4 7V17L12 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <h2>Welcome Back</h2>
              <p>Sign in to access your agent dashboard</p>
            </div>

            <div className="tabs">
              <button 
                className={`tab ${activeTab === 'login' ? 'active' : ''}`}
                onClick={() => setActiveTab('login')}
              >
                Sign In
              </button>
              <button 
                className={`tab ${activeTab === 'sso' ? 'active' : ''}`}
                onClick={() => setActiveTab('sso')}
              >
                SSO Login
              </button>
            </div>

            <form onSubmit={handleSubmit} className="login-form">
              <div className="form-group slide-up-1">
                <label htmlFor="email">Email Address</label>
                <div className="input-wrapper">
                  <span className="input-icon">✉</span>
                  <input
                    type="email"
                    id="email"
                    placeholder="priyanshu@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-group slide-up-2">
                <div className="password-header">
                  <label htmlFor="password">Password</label>
                  <a href="#" className="forgot-password">Forgot password?</a>
                </div>
                <div className="input-wrapper">
                  <span className="input-icon">🔑</span>
                  <input
                    type="password"
                    id="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
              </div>

              <button type="submit" className="btn-primary slide-up-3">
                Authenticate
                <span className="btn-arrow">→</span>
              </button>
            </form>

            <div className="login-divider slide-up-4">
              <span>or connect via</span>
            </div>

            <div className="social-logins slide-up-4">
              <button className="btn-icon" type="button" title="LinkedIn">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                </svg>
              </button>
              <button className="btn-icon" type="button" title="Google">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;