package org.opentraffic.reporter;

import org.apache.commons.cli.CommandLine;
import org.apache.kafka.streams.processor.Processor;
import org.apache.kafka.streams.processor.ProcessorContext;
import org.apache.kafka.streams.processor.ProcessorSupplier;
import org.apache.log4j.Logger;

//here we just take the incoming message, reformat it and key it while doing so
public class KeyedFormattingProcessor implements ProcessorSupplier<String, String> {
  private final static Logger logger = Logger.getLogger(KeyedFormattingProcessor.class);
  private Formatter formatter;
  public KeyedFormattingProcessor(CommandLine cmd) {
    logger.debug("Instantiating keyed formatting processor");
    String format = cmd.getOptionValue("formatter");
    formatter = Formatter.GetFormatter(format);
  }
  
  @Override
  public Processor<String, String> get() {
    return new Processor<String, String>() {
      private ProcessorContext context;

      @Override
      public void init(ProcessorContext context) {
        this.context = context;
      }

      @Override
      public void process(String key, String value) {
        try {
          Pair<String, Point> kv = formatter.format(value);
          context.forward(kv.first, kv.second);
        } catch (Exception e) {
          logger.error("Could not key and format using, key = " + key + ", value = " + value);
        }
        context.commit();
      }

      @Override
      public void punctuate(long timestamp) {
      }

      @Override
      public void close() {
      }
    };
  }
}
