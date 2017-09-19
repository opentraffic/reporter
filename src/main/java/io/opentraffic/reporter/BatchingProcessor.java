package io.opentraffic.reporter;

import org.apache.commons.cli.CommandLine;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.processor.Processor;
import org.apache.kafka.streams.processor.ProcessorContext;
import org.apache.kafka.streams.processor.ProcessorSupplier;
import org.apache.kafka.streams.processor.StateStoreSupplier;
import org.apache.kafka.streams.state.KeyValueIterator;
import org.apache.kafka.streams.state.KeyValueStore;
import org.apache.kafka.streams.state.Stores;
import org.apache.log4j.Logger;

import com.fasterxml.jackson.databind.JsonNode;

//here we just take the incoming message, reformat it and key it while doing so
public class BatchingProcessor implements ProcessorSupplier<String, Point> {
  
  private static final String BATCH_STORE_NAME = "batch";
  public static StateStoreSupplier<?> GetStore() {
     return Stores.create(BATCH_STORE_NAME).withStringKeys().withValues(new Batch.Serder()).inMemory().build();
  }
  
  //TODO: get these magic constants from arguments
  private final static Logger logger = Logger.getLogger(BatchingProcessor.class);
  private final long REPORT_TIME = 60;   //seconds
  private final int REPORT_COUNT = 10;   //number of points
  private final int REPORT_DIST = 500;   //meters
  private final long SESSION_GAP = 60000;//milliseconds
  private final String url;

  public BatchingProcessor(CommandLine cmd) {
    logger.debug("Instantiating batching processor");
    url = cmd.getOptionValue("reporter-url");
  }
  
  @Override
  public Processor<String, Point> get() {
    return new Processor<String, Point>() {
      private ProcessorContext context;
      private KeyValueStore<String, Batch> store;
  
      @SuppressWarnings("unchecked")
      @Override
      public void init(ProcessorContext context) {
        this.context = context;
        this.store = (KeyValueStore<String, Batch>) context.getStateStore(BATCH_STORE_NAME);
        context.schedule(SESSION_GAP * 2);
      }
  
      @Override
      public void process(String key, Point point) {
        //get this batch out of storage and update it
        Batch batch = store.delete(key);
        if(batch == null) {
          logger.debug("Starting new batch for " + key);
          batch = new Batch(point);
        }//we have more than one point now
        else {
          batch.update(point);
          int length = batch.points.size();
          int reported = forward(batch.report(key, url, REPORT_DIST, REPORT_COUNT, REPORT_TIME));
          if(reported > 0)
            logger.debug("Reported on " + reported + " segment pairs");
          if(batch.points.size() != length)
            logger.debug(key + " was trimmed from " + length + " down to " + batch.points.size());
        }
        
        //put it back if it has something
        if(batch.points.size() > 0) {
          batch.last_update = context.timestamp();
          store.put(key, batch);
        }
        
        //move on
        context.commit();
      }
      
      @Override
      public void punctuate(long timestamp) {
        //find which ones need to go
        KeyValueIterator<String, Batch> it = store.all();
        while(it.hasNext()) {
          KeyValue<String, Batch> kv = it.next();
          //nothing to do with this one
          if(kv.value == null) {
            store.delete(kv.key);
          }//off to the glue factory with you
          else if(timestamp - kv.value.last_update > SESSION_GAP) {
            logger.debug("Evicting " + kv.key + " as it was stale");
            store.delete(kv.key);
            //report what we can if we can
            int reported = forward(kv.value.report(kv.key, url, 0, 2, 0));
            if(reported > 0)
              logger.debug("Reported on " + reported + " segment pairs during eviction");
          }
        }
        it.close();
      }
      
      private int forward(JsonNode result) {
        JsonNode datastore = result != null ? result.get("datastore") : null;
        JsonNode reports = datastore != null ? datastore.get("reports") : null;
        int reported = 0;
        //TODO: dont ignore the mode...
        //forward on each segment pair
        if(reports != null) {
          for(JsonNode report : reports) {
            try {
              //make a segment pair with one observation
              JsonNode next_id = report.get("next_id");
              Segment segment = new Segment(report.get("id").asLong(),
                  next_id == null || next_id.isNull() ? null : next_id.asLong(), 
                  report.get("t0").asDouble(), report.get("t1").asDouble(),
                  report.get("length").asInt(), report.get("queue_length").asInt());
              //the key is the segment pair so processors will only ever see certain tiles
              //this seeks to maximize the number of possible segments in a given tile
              if(segment.valid()) {
                context.forward(Long.toString(segment.id) + ' ' +  Long.toString(segment.next_id), segment);
                reported++;
              }
              else
                logger.warn("Got back invalid segment: " + segment.toString());
            }
            catch(Exception e) {
              logger.error("Unusable reported segment pair: " + report.toString() + " (" + e.getMessage() + ")");
            }
          }
        }//we got something unexpected
        else if(result != null) {
          logger.error("Unusable report " + result.toString());
        }
        return reported;
      }
  
      @Override
      public void close() {
      }
    };
  }
}
