import React, { useRef, useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Eye,
  Mic,
  ArrowRight,
  Scan,
  MessageSquare,
  Zap,
  ShieldAlert,
  Banknote,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useVoice } from '../context/VoiceNavigationContext';

const LandingPage = () => {
  const navigate = useNavigate();
  const { toggleListening, isListening, speak } = useVoice();
  const featuresRef = useRef(null);

  // --- AUDIO & INTERACTION LOGIC (The "Fix") ---
  const [interacted, setInteracted] = useState(false);

  const startExperience = () => {
    if (!interacted) {
      setInteracted(true);
      // Play Audio immediately now that user has interacted
      speak("Welcome to Virtual Eye. I am ready. Press Spacebar to activate voice commands.");
    }
  };

  const scrollToFeatures = () => {
    featuresRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Keyboard shortcut listener for Spacebar specific to Landing Page
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.code === 'Space') {
        e.preventDefault(); // Stop page scroll
        if (!interacted) startExperience(); // Wake up audio context
        toggleListening(); // Toggle Mic
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [interacted, toggleListening]); // Dependencies ensure fresh state

  const features = [
    {
      icon: Scan,
      title: 'Live Object Detection',
      desc: 'Real-time identification of obstacles, people, and objects to ensure safe navigation.',
    },
    {
      icon: MessageSquare,
      title: 'Interactive AI Chatbot',
      desc: 'A conversational assistant that answers questions about your surroundings naturally.',
    },
    {
      icon: Banknote,
      title: 'Currency Recognition',
      desc: 'Instantly distinguish between currency notes to help with financial independence.',
    },
    {
      icon: Zap,
      title: 'Smart OCR Reader',
      desc: 'Extracts and reads text from menus, documents, and signboards aloud.',
    },
    {
      icon: ShieldAlert,
      title: 'Emergency SOS',
      desc: 'Voice-activated alert system that shares your location with trusted contacts.',
    },
  ];

  return (
    <div 
      className="landing-container"
      onClick={startExperience} // CRITICAL: First click anywhere wakes up audio
    >
      {/* Animated background orbs */}
      <div className="bg-orb bg-orb-1" />
      <div className="bg-orb bg-orb-2" />
      <div className="bg-orb bg-orb-3" />

      {/* NAVBAR */}
      <nav className="landing-nav">
        <div className="logo">
          <div className="logo-icon">
            <Eye size={28} />
          </div>
          <span className="logo-text">VIRTUAL EYE</span>
        </div>

        <div className="nav-actions">
          <button className="nav-link" onClick={scrollToFeatures}>
            Features
          </button>
          <button
            className="nav-cta"
            onClick={() => navigate('/dashboard')}
          >
            <span>Enter App</span>
            <ArrowRight size={16} />
          </button>
        </div>
      </nav>

      {/* HERO SECTION */}
      <main className="hero-section">
        <motion.div
          className="hero-content"
          initial={{ opacity: 0, y: 32 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        >
          <motion.h1
            className="hero-title"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15, duration: 0.7 }}
          >
            See the World <br />
            <span className="highlight">Through AI.</span>
          </motion.h1>

          <motion.p
            className="hero-subtitle"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.7 }}
          >
            An intelligent assistant designed for the visually impaired.
            <br />
            Click anywhere to start, then press <strong>Spacebar</strong> and speak.
          </motion.p>

          {/* Mic Orb */}
          <motion.button
            whileTap={{ scale: 0.9 }}
            className={`mic-orb ${isListening ? 'active' : ''}`}
            onClick={(e) => {
              e.stopPropagation(); // Prevent double firing with container click
              if(!interacted) startExperience();
              toggleListening();
            }}
          >
            <div className="mic-orb-inner">
              <Mic size={34} />
            </div>
          </motion.button>

          <div className="hero-hint">
            {isListening ? '>> LISTENING...' : 'TAP OR PRESS SPACE'}
          </div>
        </motion.div>
      </main>

      {/* FEATURES SECTION */}
      <section ref={featuresRef} className="features-section">
        <motion.div
          className="features-header"
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7 }}
        >
          <h2>Powerful Features</h2>
          <p>Everything needed for visual independence.</p>
        </motion.div>

        <div className="features-grid">
          {features.map((feature, idx) => (
            <motion.div
              key={idx}
              className="feature-card"
              initial={{ opacity: 0, y: 24, scale: 0.98 }}
              whileInView={{ opacity: 1, y: 0, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: idx * 0.08 }}
              whileHover={{ y: -6 }}
            >
              <div className="feature-card-glow" />
              <div className="icon-box">
                <feature.icon size={22} />
              </div>
              <h3 className="card-title">{feature.title}</h3>
              <p className="card-desc">{feature.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default LandingPage;