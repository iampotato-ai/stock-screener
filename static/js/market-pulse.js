/* static/js/market-pulse.js */
class MarketPulse {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.svg = this.container.querySelector('.market-pulse-svg');
    this.scoreEl = this.container.querySelector('.market-pulse-score');
    this.deltaEl = this.container.querySelector('.market-pulse-delta');
    this.speed = options.speed || 0.02;
    this.particleCount = options.particleCount || 20;
    this.particles = [];
    this.score = options.initialScore || 50;

    this.init();
    this.animate();
  }

  init() {
    // Create particles
    for (let i = 0; i < this.particleCount; i++) {
      this.particles.push({
        x: Math.random() * 100,
        y: Math.random() * 100,
        radius: Math.random() * 2 + 1,
        speedX: (Math.random() - 0.5) * this.speed * 10,
        speedY: (Math.random() - 0.5) * this.speed * 10,
        opacity: Math.random() * 0.6 + 0.2
      });
    }

    // Initial render
    this.render();
  }

  updateScore(score, delta) {
    this.score = Math.max(0, Math.min(100, score));
    this.scoreEl.textContent = this.score;
    this.deltaEl.textContent = delta >= 0 ? `▲ ${delta}` : `▼ ${Math.abs(delta)}`;
    this.deltaEl.className = `market-pulse-delta ${delta >= 0 ? 'positive' : 'negative'}`;

    // Adjust particle speed based on score (more energy = faster movement)
    const speedFactor = 0.5 + (this.score / 100) * 1.5;
    this.particles.forEach(p => {
      p.speedX = (p.speedX / Math.abs(p.speedX || 0.1)) * Math.random() * this.speed * speedFactor * 10;
      p.speedY = (p.speedY / Math.abs(p.speedY || 0.1)) * Math.random() * this.speed * speedFactor * 10;
    });

    // Dispatch custom event for external listeners
    this.container.dispatchEvent(new CustomEvent('market-pulse-update', {
      detail: { score: this.score, delta: delta }
    }));
  }

  render() {
    // Clear SVG
    this.svg.innerHTML = '';

    // Draw particles
    this.particles.forEach(p => {
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', p.x);
      circle.setAttribute('cy', p.y);
      circle.setAttribute('r', p.radius);
      circle.setAttribute('fill', `var(--color-accent)`);
      circle.setAttribute('opacity', p.opacity);
      this.svg.appendChild(circle);
    });

    // Draw circular background track
    const track = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    track.setAttribute('cx', '60');
    track.setAttribute('cy', '60');
    track.setAttribute('r', '50');
    track.setAttribute('fill', 'none');
    track.setAttribute('stroke', `rgba(245, 158, 11, 0.2)`);
    track.setAttribute('stroke-width', '8');
    this.svg.appendChild(track);

    // Draw score arc (progress indicator)
    const arc = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    const endAngle = (this.score / 100) * 2 * Math.PI;
    const largeArc = this.score > 50 ? '1' : '0';
    const d = `
      M 60,10
      A 50,50 0 ${largeArc} 1
      ${60 + 50 * Math.sin(endAngle)},${60 - 50 * Math.cos(endAngle)}
    `;
    arc.setAttribute('d', d.trim());
    arc.setAttribute('fill', 'none');
    arc.setAttribute('stroke', `var(--color-accent)`);
    arc.setAttribute('stroke-width', '6');
    arc.setAttribute('stroke-linecap', 'round');
    this.svg.appendChild(arc);
  }

  animate() {
    // Update particle positions
    this.particles.forEach(p => {
      p.x += p.speedX;
      p.y += p.speedY;

      // Wrap around boundaries
      if (p.x < 0) p.x = 120;
      if (p.x > 120) p.x = 0;
      if (p.y < 0) p.y = 120;
      if (p.y > 120) p.y = 0;
    });

    this.render();
    requestAnimationFrame(() => this.animate());
  }
}

// Auto-initialize if element exists
document.addEventListener('DOMContentLoaded', () => {
  const pulseContainer = document.getElementById('market-pulse');
  if (pulseContainer) {
    // Would normally get initial score from data attribute or JS
    // For now, initialize with sample data
    const initialScore = pulseContainer.getAttribute('data-initial-score') || 65;
    new MarketPulse('market-pulse', {
      initialScore: parseInt(initialScore),
      speed: 0.015
    });
  }
});