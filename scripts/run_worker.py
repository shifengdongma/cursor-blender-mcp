#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone Monitoring Worker for AIGV Studio.
"""

from __future__ import absolute_import

import argparse
import logging
import os
import signal
import sys
import time

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.monitoring_service import MonitoringWorker


def main():
    parser = argparse.ArgumentParser(description='AIGV Studio Monitoring Worker')
    parser.add_argument('--data-dir', default='./data', help='Data directory')
    parser.add_argument('--interval', type=int, default=5, help='Poll interval in seconds')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )
    logger = logging.getLogger(__name__)

    logger.info("Starting Monitoring Worker (data_dir=%s, interval=%ds)", args.data_dir, args.interval)

    worker = MonitoringWorker(
        data_dir=args.data_dir,
        interval_s=args.interval,
        monitor_targets=os.environ.get('MONITOR_TARGETS', ''),
        storage_targets=os.environ.get('STORAGE_TARGETS', ''),
        node_agent_urls=os.environ.get('NODE_AGENT_URLS', ''),
        node_agent_token=os.environ.get('NODE_AGENT_TOKEN', ''),
    )
    worker.start()

    # Handle signals
    def signal_handler(sig, frame):
        logger.info("Received signal %s, shutting down...", sig)
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
            if not worker._running:
                break
    except KeyboardInterrupt:
        pass

    logger.info("Monitoring Worker exited")


if __name__ == '__main__':
    main()
