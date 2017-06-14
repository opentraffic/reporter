package io.opentraffic.reporter;

import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.UUID;

import org.apache.commons.cli.CommandLine;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.log4j.Logger;

public class PrintConsumer implements Runnable {
  private final Consumer<String, String> consumer;
  private final Properties properties = new Properties();
  private final List<String> topics;
  
  private final static Logger logger = Logger.getLogger(PrintConsumer.class);

  public PrintConsumer(CommandLine cmd) {
    //let the user supply a client id so it has a known name if something goes wrong
    String client_id = cmd.getOptionValue("verbose");
    if(client_id == null)
      client_id = UUID.randomUUID().toString();
    logger.info("Starting print consumer " + client_id);
    //set set the group always the same to pick up where we left off
    properties.put(ConsumerConfig.GROUP_ID_CONFIG, "verbose_reporters");
    properties.put(ConsumerConfig.CLIENT_ID_CONFIG, client_id); 
    properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
    properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, cmd.getOptionValue("bootstrap"));
    properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
    properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
    consumer = new KafkaConsumer<String, String>(properties);
    this.topics = new ArrayList<String>();
    this.topics.add(cmd.getOptionValue("leaf-topic"));
  }
  
  @Override
  public void run(){
    consumer.subscribe(topics);
    while(true) {
      ConsumerRecords<String, String> records = consumer.poll(Long.MAX_VALUE);
      for(ConsumerRecord<String, String> record : records)
        System.out.println(record.key() + " " + record.value());
    }
  }
}
