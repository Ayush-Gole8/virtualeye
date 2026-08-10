import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Eye, FileText, Mic, ShieldAlert } from 'lucide-react';

const ActionCard = ({ title, desc, icon: Icon, className, onClick, delay }) => (
  <motion.button
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ delay }}
    onClick={onClick}
    className={`action-card ${className}`}
  >
    <div className="card-icon-wrapper">
      <Icon size={24} />
    </div>
    <h3 className="action-title">{title}</h3>
    <p className="action-desc">{desc}</p>
  </motion.button>
);

const DashboardHome = () => {
  const navigate = useNavigate();

  return (
    <div className="dashboard-home">
      <div className="welcome-banner">
        <h1>Good Morning.</h1>
        <p>System is active. Say <strong>"Live Vision"</strong> to start.</p>
      </div>

      <div className="dashboard-grid">
        <ActionCard 
          title="Live Vision" 
          desc="Identify objects in real-time."
          icon={Eye}
          className="card-blue"
          onClick={() => navigate('/dashboard/vision')}
          delay={0.1}
        />
        <ActionCard 
          title="Smart Reader" 
          desc="Read text from documents."
          icon={FileText}
          className="card-green"
          onClick={() => navigate('/dashboard/ocr')}
          delay={0.2}
        />
        <ActionCard 
          title="Voice Chat" 
          desc="Ask AI questions."
          icon={Mic}
          className="card-purple"
          onClick={() => navigate('/dashboard/chat')}
          delay={0.3}
        />
        <ActionCard 
          title="Emergency SOS" 
          desc="Share location immediately."
          icon={ShieldAlert}
          className="card-red"
          onClick={() => alert("SOS Triggered!")}
          delay={0.4}
        />
      </div>
    </div>
  );
};

export default DashboardHome;